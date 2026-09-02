import re

with open("frontend/src/pages/Transactions.tsx", "r") as f:
    text = f.read()

# Add search term state
if "const [search, setSearch] = useState('');" not in text:
    text = text.replace("const [loading, setLoading] = useState(true);", "const [loading, setLoading] = useState(true);\n  const [search, setSearch] = useState('');")

# Update getTransactions to include search
text = text.replace("getTransactions({ limit, offset: page * limit })", "getTransactions({ limit, offset: page * limit, transaction_id: search || undefined })")

# Update useEffect dependency to include search
text = text.replace("}, [page]);", "}, [page, search]);")

# Replace the disabled search input
search_input = """<input 
              type="text" 
              placeholder="Search transaction ID..." 
              className="bg-slate-900 border border-slate-700/60 text-slate-200 text-sm rounded-md pl-9 pr-4 py-1.5 focus:outline-none focus:border-blue-500 transition-colors w-64 placeholder:text-slate-600"
              disabled
            />"""
replace_input = """<input 
              type="text" 
              placeholder="Search transaction ID..." 
              className="bg-slate-900 border border-slate-700/60 text-slate-200 text-sm rounded-md pl-9 pr-4 py-1.5 focus:outline-none focus:border-blue-500 transition-colors w-64 placeholder:text-slate-600"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && data.length === 1) {
                  window.location.href = `/transactions/${data[0].assessment_id}`;
                }
              }}
            />"""
if search_input in text:
    text = text.replace(search_input, replace_input)

with open("frontend/src/pages/Transactions.tsx", "w") as f:
    f.write(text)
print("Patched frontend search.")
