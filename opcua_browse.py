"""OPC UA address-space browsing for PLC tag selection."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable

from asyncua import Client, ua

logger = logging.getLogger(__name__)

BROWSE_TIMEOUT_SEC = 30.0


@dataclass
class BrowseNode:
    node_id: str
    browse_name: str
    display_name: str
    node_class: str
    has_children: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BROWSE_PAGE_LIMIT = 100


def _reference_to_browse_node(ref: Any) -> BrowseNode | None:
    try:
        node_class_val = ref.NodeClass
        node_class = ua.NodeClass(node_class_val) if isinstance(node_class_val, int) else node_class_val
        browse_name = ref.BrowseName.Name if ref.BrowseName else ""
        display_name = ref.DisplayName.Text if ref.DisplayName else browse_name
        child_id = ref.NodeId.to_string()
        # Folders and array/struct variables (AI, AI[7]) must stay expandable.
        # Methods have no tag children.
        has_children = node_class != ua.NodeClass.Method
        return BrowseNode(
            node_id=child_id,
            browse_name=browse_name,
            display_name=display_name,
            node_class=node_class.name,
            has_children=has_children,
        )
    except Exception as exc:
        logger.debug("Skip browse reference %s: %s", ref, exc)
        return None


async def _browse_references(client: Client, node_id: str) -> list[Any]:
    """Read every child, following Browse continuation points from the PLC."""
    node = client.get_node(node_id)
    description = ua.BrowseDescription()
    description.NodeId = node.nodeid
    description.ResultMask = ua.BrowseResultMask.All

    parameters = ua.BrowseParameters()
    parameters.View = ua.ViewDescription()
    parameters.RequestedMaxReferencesPerNode = 0
    parameters.NodesToBrowse = [description]

    results = await asyncio.wait_for(client.uaclient.browse(parameters), timeout=BROWSE_TIMEOUT_SEC)
    browse_result = results[0]
    if browse_result.StatusCode.is_bad():
        raise RuntimeError(f"Browse failed: {browse_result.StatusCode}")

    references = list(browse_result.References or [])
    pages = 0
    while browse_result.ContinuationPoint and pages < BROWSE_PAGE_LIMIT:
        pages += 1
        next_parameters = ua.BrowseNextParameters()
        next_parameters.ReleaseContinuationPoints = False
        next_parameters.ContinuationPoints = [browse_result.ContinuationPoint]
        next_results = await asyncio.wait_for(
            client.uaclient.browse_next(next_parameters),
            timeout=BROWSE_TIMEOUT_SEC,
        )
        browse_result = next_results[0]
        if browse_result.StatusCode.is_bad():
            logger.warning(
                "BrowseNext остановился на %s: %s",
                node_id,
                browse_result.StatusCode,
            )
            break
        references.extend(browse_result.References or [])
    return references


async def browse_children(client: Client, node_id: str) -> list[BrowseNode]:
    """Return all direct children of an OPC UA node."""
    references = await _browse_references(client, node_id)
    result: list[BrowseNode] = []
    for ref in references:
        item = _reference_to_browse_node(ref)
        if item is not None:
            result.append(item)
    result.sort(key=lambda item: item.browse_name.lower())
    return result


async def test_opcua_connection(url: str, timeout: float = 8.0) -> str:
    """Connect briefly and return server name to verify controller reachability."""
    client = Client(url=url.strip())
    await asyncio.wait_for(client.connect(), timeout=timeout)
    try:
        server_node = client.get_node(ua.ObjectIds.Server)
        display_name = (await server_node.read_display_name()).Text
        return display_name or "Связь установлена"
    finally:
        await client.disconnect()


def test_opcua_connection_async(
    url: str,
    on_ok: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    """Run connection test in a background thread."""

    def _worker() -> None:
        try:
            message = asyncio.run(test_opcua_connection(url))
            on_ok(message)
        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_worker, name="opcua-link-test", daemon=True).start()


READ_TIMEOUT_SEC = 5.0
SEARCH_MAX_DEPTH = 24
SEARCH_MAX_BROWSE_OPS = 8000
RESOLVE_LIST_TIMEOUT_SEC = 90.0
# OWEN210: tags live under Resources/Application/GlobalVars (GVL_* subfolders), not directly under PLC210.
FAST_TAG_PATHS = [
    ["DeviceSet", "PLC210 OPC-UA", "Resources", "Application", "GlobalVars"],
    ["DeviceSet", "PLC210 OPC-UA", "Resources", "Application"],
    ["DeviceSet", "PLC210 OPC-UA"],
    ["DeviceSet"],
]
# Type-definition branches (e.g. BaseObjectType under DeviceSet) contain no PLC tag instances.
SKIP_DESCENT_NODE_CLASSES = frozenset({"ObjectType", "View", "Method", "ReferenceType", "DataType", "VariableType"})

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class TagResolveCancelled(Exception):
    """Raised when the user cancels tag list resolution."""


def _format_resolve_error(exc: BaseException) -> str:
    if isinstance(exc, TagResolveCancelled):
        return str(exc) or "Загрузка отменена"
    if isinstance(exc, asyncio.TimeoutError):
        return f"Превышено время ожидания ответа от контроллера ({RESOLVE_LIST_TIMEOUT_SEC:.0f} с)"
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}: неизвестная ошибка"


def looks_like_opcua_node_id(value: str) -> bool:
    """Return True if the string looks like an OPC UA NodeId, not a tag name."""
    text = value.strip().lower()
    if not text:
        return False
    if text.startswith("ns="):
        return True
    if text.startswith(("i=", "s=", "g=", "b=")):
        return True
    return any(token in text for token in (";i=", ";s=", ";g=", ";b="))


def _child_name_matches(child: BrowseNode, name: str) -> bool:
    target = name.strip().lower()
    if not target:
        return False
    for key in (child.browse_name, child.display_name):
        if key and key.lower() == target:
            return True
    return False


def _should_descend_into(child: BrowseNode) -> bool:
    # Name search stays on folders. Array elements are opened in the browse tree.
    if child.node_class == "Variable" or child.node_class in SKIP_DESCENT_NODE_CLASSES:
        return False
    return child.has_children


async def _navigate_by_path(
    client: Client,
    root_id: str,
    path_names: list[str],
    *,
    browse_ops: list[int],
    max_browse_ops: int,
    cancel_check: CancelCheck | None = None,
) -> str | None:
    node_id = root_id
    for name in path_names:
        if cancel_check and cancel_check():
            raise TagResolveCancelled("Загрузка отменена пользователем")
        if browse_ops[0] >= max_browse_ops:
            return None
        try:
            children = await browse_children(client, node_id)
        except Exception as exc:
            logger.debug("Navigate skip %s: %s", node_id, exc)
            return None
        browse_ops[0] += 1
        match = next((child for child in children if _child_name_matches(child, name)), None)
        if match is None:
            return None
        node_id = match.node_id
    return node_id


async def _find_tags_by_names(
    client: Client,
    root_id: str,
    names: list[str],
    *,
    max_depth: int = SEARCH_MAX_DEPTH,
    max_browse_ops: int = SEARCH_MAX_BROWSE_OPS,
    on_progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    progress_base: int = 5,
    progress_span: int = 75,
) -> dict[str, BrowseNode]:
    """Find Variables by browse/display name; stop when all names are found."""
    pending = {name.strip().lower() for name in names if name.strip()}
    found: dict[str, BrowseNode] = {}
    if not pending:
        return found

    browse_ops = [0]
    last_progress_ops = [0]
    last_progress_found = [0]

    def report_progress(stage: str, *, force: bool = False) -> None:
        if on_progress is None:
            return
        if (
            not force
            and browse_ops[0] - last_progress_ops[0] < 30
            and len(found) == last_progress_found[0]
        ):
            return
        last_progress_ops[0] = browse_ops[0]
        last_progress_found[0] = len(found)
        ops_ratio = min(1.0, browse_ops[0] / max(max_browse_ops, 1))
        pct = progress_base + int(progress_span * ops_ratio)
        on_progress(
            min(progress_base + progress_span, pct),
            f"{stage}: найдено {len(found)} из {len(pending)}",
        )

    def collect_matches(children: list[BrowseNode]) -> None:
        for child in children:
            if len(found) >= len(pending):
                return
            if child.node_class != "Variable":
                continue
            for key in (child.browse_name, child.display_name):
                if not key:
                    continue
                key_lower = key.lower()
                if key_lower in pending and key_lower not in found:
                    found[key_lower] = child
                    break

    async def walk(node_id: str, depth: int) -> None:
        if cancel_check and cancel_check():
            raise TagResolveCancelled("Загрузка отменена пользователем")
        if depth > max_depth or len(found) >= len(pending) or browse_ops[0] >= max_browse_ops:
            return
        try:
            children = await browse_children(client, node_id)
        except Exception as exc:
            logger.debug("Name search skip %s: %s", node_id, exc)
            return
        browse_ops[0] += 1
        collect_matches(children)
        report_progress("Поиск по дереву")

        if len(found) >= len(pending):
            return

        for child in children:
            if cancel_check and cancel_check():
                raise TagResolveCancelled("Загрузка отменена пользователем")
            if len(found) >= len(pending) or browse_ops[0] >= max_browse_ops:
                return
            if _should_descend_into(child):
                await walk(child.node_id, depth + 1)

    report_progress("Быстрый поиск", force=True)
    for path in FAST_TAG_PATHS:
        if len(found) >= len(pending):
            break
        start_id = await _navigate_by_path(
            client,
            root_id,
            path,
            browse_ops=browse_ops,
            max_browse_ops=max_browse_ops,
            cancel_check=cancel_check,
        )
        if start_id is None:
            continue
        report_progress(f"Поиск в {' → '.join(path)}", force=True)
        await walk(start_id, 0)

    if len(found) < len(pending) and browse_ops[0] < max_browse_ops:
        report_progress("Полный обход дерева", force=True)
        await walk(root_id, 0)

    report_progress("Готово", force=True)
    return found

def _pick_best_name_match(candidates: list[BrowseNode]) -> BrowseNode | None:
    if not candidates:
        return None
    variables = [node for node in candidates if node.node_class == "Variable"]
    if variables:
        return variables[0]
    return candidates[0]


def _node_entry_from_browse(node: BrowseNode, *, query: str, ok: bool = True) -> dict[str, Any]:
    return {
        "query": query,
        "node_id": node.node_id,
        "ok": ok,
        "browse_name": node.browse_name,
        "display_name": node.display_name or node.browse_name,
        "node_class": node.node_class,
    }


async def resolve_tag_list_entries(
    url: str,
    entries: list[tuple[str, str | None]],
    *,
    connect_timeout: float = 8.0,
    read_timeout: float = READ_TIMEOUT_SEC,
    max_depth: int = SEARCH_MAX_DEPTH,
    resolve_timeout: float = RESOLVE_LIST_TIMEOUT_SEC,
    on_progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> list[dict[str, Any]]:
    """Resolve file rows by NodeId or by tag name (browse/display name)."""

    async def _resolve(client: Client) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        root_id = client.nodes.objects.nodeid.to_string()
        name_queries: list[str] = []

        for query, _local in entries:
            query = query.strip()
            if not query:
                continue
            if not looks_like_opcua_node_id(query):
                name_queries.append(query)

        if on_progress is not None:
            on_progress(3, "Подключено к контроллеру")

        name_matches: dict[str, BrowseNode] = {}
        if name_queries:
            if on_progress is not None:
                on_progress(5, f"Поиск {len(name_queries)} имён на контроллере…")
            raw_matches = await _find_tags_by_names(
                client,
                root_id,
                name_queries,
                max_depth=max_depth,
                on_progress=on_progress,
                cancel_check=cancel_check,
                progress_base=5,
                progress_span=75,
            )
            for query in name_queries:
                match = raw_matches.get(query.lower())
                if match is not None:
                    name_matches[query.lower()] = match

        node_id_total = sum(1 for query, _local in entries if query.strip() and looks_like_opcua_node_id(query.strip()))
        node_id_done = 0
        for query, _local in entries:
            query = query.strip()
            if not query:
                continue
            if cancel_check and cancel_check():
                raise TagResolveCancelled("Загрузка отменена пользователем")

            entry: dict[str, Any] = {
                "query": query,
                "node_id": "",
                "ok": False,
                "browse_name": "",
                "display_name": "",
                "node_class": "",
            }
            if looks_like_opcua_node_id(query):
                node_id_done += 1
                if on_progress is not None and node_id_total:
                    pct = 82 + int(16 * node_id_done / node_id_total)
                    on_progress(min(98, pct), f"Чтение NodeId {node_id_done} из {node_id_total}…")
                try:
                    node = client.get_node(query)
                    browse_name = await asyncio.wait_for(node.read_browse_name(), timeout=read_timeout)
                    display_name = await asyncio.wait_for(node.read_display_name(), timeout=read_timeout)
                    node_class = await asyncio.wait_for(node.read_node_class(), timeout=read_timeout)
                    entry["node_id"] = query
                    entry["browse_name"] = browse_name.Name if browse_name else ""
                    entry["display_name"] = display_name.Text if display_name else entry["browse_name"]
                    entry["node_class"] = node_class.name if hasattr(node_class, "name") else str(node_class)
                    entry["ok"] = True
                except Exception as exc:
                    entry["error"] = str(exc)
                    logger.debug("Resolve NodeId failed %s: %s", query, exc)
                resolved.append(entry)
                continue

            match = name_matches.get(query.lower())
            if match is None:
                entry["error"] = (
                    f"Имя «{query}» не найдено на контроллере "
                    "(проверьте имя в дереве «Опрос» или укажите NodeId)"
                )
                resolved.append(entry)
                continue
            resolved.append(_node_entry_from_browse(match, query=query))

        if on_progress is not None:
            on_progress(100, "Готово")
        return resolved

    client = Client(url=url.strip())
    await asyncio.wait_for(client.connect(), timeout=connect_timeout)
    try:
        return await asyncio.wait_for(_resolve(client), timeout=resolve_timeout)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"Превышено время поиска тегов ({resolve_timeout:.0f} с). "
            "Укажите NodeId в файле или сократите список."
        ) from exc
    finally:
        await client.disconnect()


def resolve_tag_list_entries_async(
    url: str,
    entries: list[tuple[str, str | None]],
    on_done: Callable[[list[dict[str, Any]]], None],
    on_error: Callable[[str], None],
    on_progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> None:
    """Resolve tag list file rows in a background thread."""

    def _worker() -> None:
        try:
            resolved = asyncio.run(
                resolve_tag_list_entries(
                    url,
                    entries,
                    on_progress=on_progress,
                    cancel_check=cancel_check,
                )
            )
            on_done(resolved)
        except Exception as exc:
            on_error(_format_resolve_error(exc))

    threading.Thread(target=_worker, name="opcua-tag-resolve", daemon=True).start()


async def verify_opcua_tags(
    url: str,
    node_ids: list[str],
    *,
    connect_timeout: float = 8.0,
    read_timeout: float = READ_TIMEOUT_SEC,
) -> dict[str, str]:
    """Try to read each tag; return node_id -> «Связь» or «Нет связи»."""
    client = Client(url=url.strip())
    await asyncio.wait_for(client.connect(), timeout=connect_timeout)
    results: dict[str, str] = {}
    try:
        for node_id in node_ids:
            node_id = node_id.strip()
            if not node_id:
                continue
            try:
                node = client.get_node(node_id)
                await asyncio.wait_for(node.read_value(), timeout=read_timeout)
                results[node_id] = "Связь"
            except Exception as exc:
                logger.debug("Tag read failed %s: %s", node_id, exc)
                results[node_id] = "Нет связи"
    finally:
        await client.disconnect()
    return results


def verify_opcua_tags_async(
    url: str,
    node_ids: list[str],
    on_done: Callable[[dict[str, str]], None],
    on_error: Callable[[str], None],
) -> None:
    """Verify tag readability in a background thread."""

    def _worker() -> None:
        try:
            results = asyncio.run(verify_opcua_tags(url, node_ids))
            on_done(results)
        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_worker, name="opcua-tag-verify", daemon=True).start()


async def resolve_opcua_node_ids(
    url: str,
    node_ids: list[str],
    *,
    connect_timeout: float = 8.0,
    read_timeout: float = READ_TIMEOUT_SEC,
) -> list[dict[str, Any]]:
    """Read metadata for each NodeId on the controller."""
    client = Client(url=url.strip())
    await asyncio.wait_for(client.connect(), timeout=connect_timeout)
    resolved: list[dict[str, Any]] = []
    try:
        for node_id in node_ids:
            node_id = node_id.strip()
            if not node_id:
                continue
            entry: dict[str, Any] = {
                "query": node_id,
                "node_id": node_id,
                "ok": False,
                "browse_name": "",
                "display_name": "",
                "node_class": "",
            }
            try:
                node = client.get_node(node_id)
                browse_name = await asyncio.wait_for(node.read_browse_name(), timeout=read_timeout)
                display_name = await asyncio.wait_for(node.read_display_name(), timeout=read_timeout)
                node_class = await asyncio.wait_for(node.read_node_class(), timeout=read_timeout)
                entry["browse_name"] = browse_name.Name if browse_name else ""
                entry["display_name"] = display_name.Text if display_name else entry["browse_name"]
                entry["node_class"] = node_class.name if hasattr(node_class, "name") else str(node_class)
                entry["ok"] = True
            except Exception as exc:
                entry["error"] = str(exc)
                logger.debug("Resolve node failed %s: %s", node_id, exc)
            resolved.append(entry)
    finally:
        await client.disconnect()
    return resolved


def resolve_opcua_node_ids_async(
    url: str,
    node_ids: list[str],
    on_done: Callable[[list[dict[str, Any]]], None],
    on_error: Callable[[str], None],
) -> None:
    """Resolve NodeId metadata in a background thread."""

    def _worker() -> None:
        try:
            resolved = asyncio.run(resolve_opcua_node_ids(url, node_ids))
            on_done(resolved)
        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_worker, name="opcua-tag-resolve", daemon=True).start()


class OpcUaBrowserSession:
    """Persistent background browse session for one OPC UA server."""

    def __init__(
        self,
        on_children: Callable[[str, list[dict[str, Any]]], None],
        on_connected: Callable[[], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._on_children = on_children
        self._on_connected = on_connected
        self._on_error = on_error
        self._url = ""
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Client | None = None
        self._queue: asyncio.Queue[tuple[str, str]] | None = None
        self._stop_event = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def connect(self, url: str) -> None:
        self.close()
        self._stop_event.clear()
        self._url = url.strip()
        self._thread = threading.Thread(target=self._run, name="opcua-browse", daemon=True)
        self._thread.start()

    def browse(self, node_id: str) -> None:
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None:
            return
        asyncio.run_coroutine_threadsafe(queue.put(("browse", node_id)), loop)

    def close(self) -> None:
        self._stop_event.set()
        loop = self._loop
        queue = self._queue
        if loop is not None and queue is not None:
            asyncio.run_coroutine_threadsafe(queue.put(("stop", "")), loop)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._queue = None
        self._client = None

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception as exc:
            self._on_error(str(exc))

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        client: Client | None = None
        try:
            client = Client(url=self._url)
            self._client = client
            await client.connect()
            root_id = client.nodes.objects.nodeid.to_string()
            children = await browse_children(client, root_id)
            self._on_children(root_id, [node.to_dict() for node in children])
            self._on_connected()

            while not self._stop_event.is_set():
                try:
                    command, node_id = await asyncio.wait_for(self._queue.get(), timeout=0.4)
                except asyncio.TimeoutError:
                    continue
                if command == "stop":
                    break
                if command == "browse":
                    try:
                        children = await asyncio.wait_for(
                            browse_children(client, node_id),
                            timeout=BROWSE_TIMEOUT_SEC + 10,
                        )
                        self._on_children(node_id, [node.to_dict() for node in children])
                    except asyncio.TimeoutError:
                        self._on_error(f"Таймаут опроса узла ({BROWSE_TIMEOUT_SEC:.0f} с)")
                    except Exception as exc:
                        self._on_error(str(exc))
        except Exception as exc:
            self._on_error(str(exc))
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._loop = None
            self._queue = None
