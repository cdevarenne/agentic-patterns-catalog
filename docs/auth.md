# Authentication and Remote Access

This document explains how to configure and run the Model Context Protocol (MCP) server over HTTP with Google OAuth.

## 1. What You Need

You need the following items in Google Cloud Console:

- A Google Cloud project.
- An OAuth consent screen set to **External** and **Testing** status, with your Google account added as a test user.
- An OAuth 2.0 Client ID of type **Web application** with the authorized redirect URI `http://localhost:8000/auth/callback`.

> [!IMPORTANT]
> You must create an OAuth client of type **Web application**. You cannot reuse an existing **Desktop** client ID (assumption from spec §6.2). Check the client type column in Google Cloud Console before you proceed.

## 2. Set the Variables

1. Copy `.env.example` to `.env`:
   ```sh
   cp .env.example .env
   ```
2. Open `.env` and set these variables:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth Client ID.
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth Client Secret.
   - `CATALOG_BASE_URL`: Base URL of the server (defaults to `http://localhost:8000`).
   - `CATALOG_ACCESS`: Comma-separated list of `email:role` pairs (for example, `you@example.com:curator`).
3. Note: The `.env` file contains secrets and is gitignored. Do not commit it.

## 3. Run

1. Install dependencies:
   ```sh
   uv sync --extra dev --extra mcp --extra embed
   ```
2. Start the HTTP server:
   ```sh
   uv run --env-file .env catalog serve --http
   ```
3. When an MCP client makes its first request, FastMCP opens your browser for Google login.
4. After you consent, the client receives a FastMCP token. The server maps this token to your verified e-mail.

## 4. What the Server Checks

The server enforces the following trust boundary rules:

- The HTTP server refuses to start if `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is missing.
- The server denies any access token that lacks a verified e-mail address.
- The resolved subject must match an entry in `CATALOG_ACCESS` with role `reader` or `curator`.
- The server writes every access decision to `var/activity.jsonl` before the tool executes.

## 5. Licence Note

The `get_pattern` tool returns cached site content (© KORTEXYA SAS, licensed for personal education). Only add subjects to `CATALOG_ACCESS` who accept these licence terms.

## 6. Manual Login Check

Once you create the Google Web application client, execute this checklist to verify remote authentication:

- [ ] Start the server: `uv run --env-file .env catalog serve --http`
- [ ] In another terminal, connect with the FastMCP client:
  ```python
  import asyncio
  from fastmcp.client import Client

  async def test_login():
      async with Client("http://localhost:8000/mcp", auth="oauth") as client:
          res = await client.call_tool("select", {"task": "route a request by meaning"})
          print("Subject:", res.structured_content["auth"]["subject"])

  asyncio.run(test_login())
  ```
- [ ] Complete the Google OAuth login prompt in your browser.
- [ ] Confirm that `auth.subject` printed in the output matches your verified Google e-mail address.
- [ ] Confirm that an `allow` decision row was appended to `var/activity.jsonl`.
