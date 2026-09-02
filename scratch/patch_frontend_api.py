with open("frontend/src/api.ts", "r") as f:
    text = f.read()

if "import.meta.env.VITE_API_KEY" not in text:
    new_code = """
const apiKey = import.meta.env.VITE_API_KEY;
if (apiKey) {
  api.defaults.headers.common['X-API-Key'] = apiKey;
}
"""
    text = text.replace("export const getSummary", new_code + "\nexport const getSummary")

with open("frontend/src/api.ts", "w") as f:
    f.write(text)
