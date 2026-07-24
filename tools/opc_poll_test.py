"""Quick OPC UA poll test for gateway at opc.tcp://172.18.0.1:4841"""
import asyncio
import sys
from datetime import datetime

URL = sys.argv[1] if len(sys.argv) > 1 else "opc.tcp://172.18.0.1:4841"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
INTERVAL = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0


async def main() -> None:
    from asyncua import Client

    print(f"Connecting to {URL} ...")
    async with Client(url=URL) as client:
        root = client.nodes.objects
        print("Connected. Browsing GatewayData variables...\n")

        # Try common paths
        vars_found = []
        try:
            gateway_folder = await root.get_child(["2:GatewayData"])
            children = await gateway_folder.get_children()
            for node in children:
                try:
                    bn = await node.read_browse_name()
                    if bn.Name:
                        vars_found.append(node)
                except Exception:
                    pass
        except Exception:
            pass

        if not vars_found:
            # fallback: browse all variables under Objects
            print("GatewayData not found, browsing Objects tree...")
            stack = [root]
            while stack and len(vars_found) < 30:
                node = stack.pop()
                try:
                    children = await node.get_children()
                except Exception:
                    continue
                for ch in children:
                    try:
                        node_class = await ch.read_node_class()
                        from asyncua import ua
                        if node_class == ua.NodeClass.Variable:
                            vars_found.append(ch)
                        elif node_class in (ua.NodeClass.Object, ua.NodeClass.ObjectType):
                            stack.append(ch)
                    except Exception:
                        pass

        if not vars_found:
            print("ERROR: No variables found on server.")
            return

        print(f"Found {len(vars_found)} variable(s). Polling {ROUNDS} times every {INTERVAL}s:\n")
        prev = {}
        for r in range(1, ROUNDS + 1):
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"--- Round {r}/{ROUNDS} @ {ts} ---")
            changed = 0
            for node in vars_found[:20]:
                try:
                    name = (await node.read_browse_name()).Name
                    val = await node.read_value()
                    key = str(name)
                    mark = ""
                    if key in prev and prev[key] != val:
                        mark = "  <-- CHANGED"
                        changed += 1
                    elif key not in prev:
                        mark = "  (first read)"
                    prev[key] = val
                    print(f"  {name}: {val!r}{mark}")
                except Exception as exc:
                    print(f"  ? read error: {exc}")
            if changed == 0 and r > 1:
                print("  (values unchanged this round — polling still OK if reads succeed)")
            print()
            if r < ROUNDS:
                await asyncio.sleep(INTERVAL)

        print("Done. If all rounds printed values — gateway publishes data.")
        print("If values never change — PLC may be static; SCADA Subscribe may look 'silent'.")


if __name__ == "__main__":
    asyncio.run(main())
