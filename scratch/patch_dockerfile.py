with open("Dockerfile.frontend", "r") as f:
    text = f.read()

search_str = "COPY --from=build /app/dist /usr/share/nginx/html"
replace_str = "COPY --from=build /app/dist /usr/share/nginx/html\n\n# Copy custom Nginx configuration for SPA routing\nCOPY frontend/nginx.conf /etc/nginx/conf.d/default.conf"

if search_str in text:
    text = text.replace(search_str, replace_str)
else:
    print("Could not find search string in Dockerfile.frontend")

with open("Dockerfile.frontend", "w") as f:
    f.write(text)
