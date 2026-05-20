import argparse
import sys
from mintry.core.wallet import MintryWallet

def print_table(headers: list[str], rows: list[list[str]]):
    if not rows:
        print("No mandates found.")
        return
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(str(cell)))
            
    # Format line template
    template = " | ".join(f"{{:<{w}}}" for w in widths)
    separator = "-+-".join("-" * w for w in widths)
    
    print(template.format(*headers))
    print(separator)
    for row in rows:
        print(template.format(*(str(c) for c in row)))

def cmd_list(args):
    wallet = MintryWallet(db_path=args.db)
    mandates = wallet.list_mandates()
    
    headers = ["Mandate ID", "Status", "Budget (USD)", "Spent (USD)", "Expiry"]
    rows = []
    for m in mandates:
        expiry_str = m["expires_at"] if m["expires_at"] else "Never"
        rows.append([
            m["id"],
            m["status"],
            f"${m['budget_usd']:.4f}",
            f"${m['spent_usd']:.4f}",
            expiry_str
        ])
    print_table(headers, rows)

def cmd_inspect(args):
    wallet = MintryWallet(db_path=args.db)
    mandate_id = args.id
    
    mandate = wallet.get_mandate(mandate_id)
    if mandate["status"] == "unknown":
        print(f"Error: Mandate '{mandate_id}' not found.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Mandate ID: {mandate_id}")
    print(f"Status:     {mandate['status']}")
    print(f"Budget:     ${mandate['budget_usd']:.4f}")
    print(f"Spent:      ${mandate['spent_usd']:.4f}")
    remaining = mandate['budget_usd'] - mandate['spent_usd']
    print(f"Remaining:  ${remaining:.4f}")
    expiry_str = mandate['expires_at'].isoformat() if mandate['expires_at'] else "Never"
    print(f"Expiry:     {expiry_str}")
    print()
    print("History/Audit Log:")
    
    logs = wallet.get_audit_log(mandate_id)
    if not logs:
        print("  No history recorded.")
    else:
        headers = ["ID", "Timestamp", "Action", "Amount", "Details"]
        rows = [
            [
                str(l["id"]),
                l["timestamp"],
                l["action"],
                f"${l['amount']:.4f}" if l["amount"] else "$0.0000",
                l["details"] or ""
            ]
            for l in logs
        ]
        print_table(headers, rows)

def main():
    parser = argparse.ArgumentParser(description="Mintry Logic Fabric CLI Utility")
    parser.add_argument(
        "--db",
        default="~/.mintry/vouchers.db",
        help="Path to the SQLite vouchers database (default: ~/.mintry/vouchers.db)"
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    # mandates command group
    mandates_parser = subparsers.add_parser("mandates", help="Manage and inspect mandates")
    mandates_subparsers = mandates_parser.add_subparsers(dest="subcommand")
    
    # mandates list subcommand
    list_parser = mandates_subparsers.add_parser("list", help="List all mandates")
    list_parser.set_defaults(func=cmd_list)
    
    # mandates inspect subcommand
    inspect_parser = mandates_subparsers.add_parser("inspect", help="Inspect a specific mandate and its audit log")
    inspect_parser.add_argument("id", help="The mandate ID to inspect")
    inspect_parser.set_defaults(func=cmd_inspect)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    elif args.command == "mandates" and not args.subcommand:
        mandates_parser.print_help()
        sys.exit(0)
        
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
