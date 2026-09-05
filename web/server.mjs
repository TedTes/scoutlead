import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("./dist/", import.meta.url)));
const indexFile = resolve(root, "index.html");
const host = process.env.HOST || "0.0.0.0";
const port = Number.parseInt(process.env.PORT || "4173", 10);

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};

const server = createServer(async (request, response) => {
  if (!["GET", "HEAD"].includes(request.method || "")) {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }

  const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
  const file = resolveRequestPath(url.pathname);
  if (!file) {
    response.writeHead(400);
    response.end("Bad request");
    return;
  }

  if (await sendFile(file, response, request.method === "HEAD")) {
    return;
  }

  if (!url.pathname.startsWith("/assets/")) {
    await sendFile(indexFile, response, request.method === "HEAD");
    return;
  }

  response.writeHead(404);
  response.end("Not found");
});

server.listen(port, host, () => {
  console.log(`ScoutLead web listening on http://${host}:${port}`);
});

function resolveRequestPath(pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }

  const resolved = resolve(root, `.${decoded === "/" ? "/index.html" : decoded}`);
  return resolved.startsWith(root) ? resolved : null;
}

async function sendFile(file, response, headOnly) {
  try {
    const fileStat = await stat(file);
    if (!fileStat.isFile()) return false;
  } catch {
    return false;
  }

  const extension = extname(file);
  response.writeHead(200, {
    "Cache-Control": extension === ".html" ? "no-cache" : "public, max-age=31536000, immutable",
    "Content-Type": contentTypes[extension] || "application/octet-stream",
    "X-Content-Type-Options": "nosniff",
  });
  if (headOnly) {
    response.end();
    return true;
  }
  createReadStream(file).pipe(response);
  return true;
}
