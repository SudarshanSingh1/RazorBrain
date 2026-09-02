import glob

for filename in ["frontend/src/pages/Transactions.tsx", "frontend/src/pages/ReviewQueue.tsx", "frontend/src/pages/AuditTrail.tsx"]:
    with open(filename, "r") as f:
        content = f.read()
    
    # Simple replace of the transaction_id cell
    search = '<td className="px-4 py-2.5 font-mono text-xs text-slate-500 group-hover:text-slate-300 transition-colors">{row.transaction_id}</td>'
    replace = '<td className="px-4 py-2.5 font-mono text-xs"><Link to={`/transactions/${row.assessment_id}`} className="text-blue-500 hover:text-blue-400 hover:underline transition-colors" title="Investigate Assessment">{row.transaction_id}</Link></td>'
    
    if search in content:
        content = content.replace(search, replace)
    
    # Also add Link import if it's missing in some files (Wait, they already have it for Inspect/Verify)
    with open(filename, "w") as f:
        f.write(content)

print("Patched links.")
