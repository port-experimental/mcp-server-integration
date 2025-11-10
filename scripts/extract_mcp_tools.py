"""
MCP Tool Extractor for Port
Automatically syncs tools from all MCP servers in Port catalog
"""
import asyncio
import json
import os
import sys
from typing import List, Dict, Any
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class PortAPIClient:
    """Client for interacting with Port API"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.getport.io/v1"
        self.access_token = None
    
    async def authenticate(self):
        """Authenticate with Port API and get access token"""
        print(f"🔐 Authenticating with Port API at {self.base_url}...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/auth/access_token",
                    json={
                        "clientId": self.client_id,
                        "clientSecret": self.client_secret
                    }
                )
                response.raise_for_status()
                data = response.json()
                self.access_token = data["accessToken"]
                print("✅ Successfully authenticated with Port API")
            except httpx.HTTPError as e:
                print(f"❌ Authentication failed: {e}")
                raise
    
    async def get_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """Fetch all MCP servers from Port"""
        if not self.access_token:
            await self.authenticate()
        
        print(f"📡 Fetching MCP servers from Port...")
        print(f"   API endpoint: {self.base_url}/blueprints/mcpRegistry/entities")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/blueprints/mcpRegistry/entities",
                    headers={"Authorization": f"Bearer {self.access_token}"}
                )
                response.raise_for_status()
                data = response.json()
                servers = data.get("entities", [])
                print(f"✅ Successfully fetched {len(servers)} MCP servers from Port")
                
                if servers:
                    print("\n📋 MCP Servers found:")
                    for idx, server in enumerate(servers, 1):
                        print(f"   {idx}. {server.get('title', 'Untitled')} (ID: {server.get('identifier')})")
                else:
                    print("⚠️  No MCP servers found in Port catalog")
                
                return servers
            except httpx.HTTPError as e:
                print(f"❌ Failed to fetch MCP servers: {e}")
                raise
    
    async def create_tool_entity(self, tool_data: Dict[str, Any], server_id: str):
        """Create or update a tool entity in Port"""
        if not self.access_token:
            await self.authenticate()
        
        # Add relation to MCP server
        tool_data["relations"] = {"mcpServer": server_id}
        tool_identifier = tool_data.get("identifier", "unknown")
        
        print(f"      📤 Creating/updating tool '{tool_identifier}' in Port...")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/blueprints/mcpToolSpecification/entities?upsert=true&merge=true",
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json"
                    },
                    json=tool_data
                )
                response.raise_for_status()
                print(f"      ✅ Successfully synced tool '{tool_identifier}'")
            except httpx.HTTPError as e:
                print(f"      ❌ Failed to sync tool '{tool_identifier}': {e}")
                raise
    
    async def update_server_tools(self, server_id: str, tool_names: List[str]):
        """Update MCP server entity with list of available tools"""
        if not self.access_token:
            await self.authenticate()
        
        print(f"   📝 Updating MCP server with {len(tool_names)} tools...")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    f"{self.base_url}/blueprints/mcpRegistry/entities/{server_id}",
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "properties": {
                            "tools": tool_names
                        }
                    }
                )
                response.raise_for_status()
                print(f"   ✅ Updated MCP server entity with tools list")
            except httpx.HTTPError as e:
                print(f"   ⚠️  Failed to update server tools: {e}")
                # Don't raise - this is not critical

def parse_command(command_str: str) -> tuple[str, List[str]]:
    """Parse command string into command and arguments"""
    import shlex
    
    # Use shlex to properly parse shell commands
    parts = shlex.split(command_str)
    
    if not parts:
        raise ValueError("Empty command string")
    
    command = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    
    return command, args

def replace_secret_placeholders(command_str: str) -> str:
    """Replace YOUR__SECRET_NAME placeholders with actual environment variable values
    
    Supports two patterns:
        1. YOUR__SECRET_NAME  -> replaces with os.getenv("SECRET_NAME")
        2. <YOUR_SECRET_NAME> -> replaces with os.getenv("SECRET_NAME")
    
    Example:
        Command: "uvx server --key YOUR__API_KEY"
        Replaces YOUR__API_KEY with value from os.getenv("API_KEY")
    """
    import re
    
    # Pattern 1: YOUR__SECRET_NAME (double underscore)
    pattern1 = r'YOUR__([A-Z_]+)'
    matches1 = re.findall(pattern1, command_str)
    
    # Pattern 2: <YOUR_SECRET_NAME> (angle brackets, single underscore)
    pattern2 = r'<YOUR_([A-Z_]+)>'
    matches2 = re.findall(pattern2, command_str)
    
    all_matches = list(set(matches1 + matches2))
    
    if all_matches:
        print(f"   🔑 Found secret placeholders: {all_matches}")
    
    for secret_name in all_matches:
        secret_value = os.getenv(secret_name)
        if secret_value:
            # Replace both patterns
            command_str = command_str.replace(f"YOUR__{secret_name}", secret_value)
            command_str = command_str.replace(f"<YOUR_{secret_name}>", secret_value)
            print(f"      ✅ Replaced placeholder with {secret_name} environment variable")
        else:
            print(f"      ⚠️  Warning: Environment variable {secret_name} not found")
    
    return command_str

async def extract_tools_from_mcp(command_str: str) -> List[Dict[str, Any]]:
    """Connect to MCP server and extract tools"""
    print(f"   🔌 Connecting to MCP server...")
    print(f"      📝 Original command: {command_str}")
    
    # Replace secret placeholders (YOUR__SECRET_NAME pattern)
    command_str_with_secrets = replace_secret_placeholders(command_str)
    print(f"      🔐 Command after secret replacement: {command_str_with_secrets[:100]}..." if len(command_str_with_secrets) > 100 else f"      🔐 Command after secret replacement: {command_str_with_secrets}")
    
    # Parse command into executable and arguments
    try:
        command, args = parse_command(command_str_with_secrets)
        print(f"      ⚙️  Executable: {command}")
        print(f"      📋 Arguments: {args[:3]}..." if len(args) > 3 else f"      📋 Arguments: {args}")
    except Exception as e:
        print(f"   ❌ Failed to parse command: {e}")
        return []
    
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=None
    )
    
    tools_data = []
    try:
        async with stdio_client(server_params) as (read, write):
            print(f"   ✅ Connected to MCP server")
            async with ClientSession(read, write) as session:
                print(f"   🔄 Initializing session...")
                await session.initialize()
                print(f"   ✅ Session initialized")
                
                # List all tools from the MCP server
                print(f"   📋 Listing tools from MCP server...")
                tools_result = await session.list_tools()
                print(f"   ✅ Found {len(tools_result.tools)} tools")
                
                for tool in tools_result.tools:
                    tool_identifier = f"{tool.name.lower().replace(' ', '_').replace('-', '_')}"
                    print(f"      - {tool.name} (ID: {tool_identifier})")
                    tools_data.append({
                        "identifier": tool_identifier,
                        "title": tool.name,
                        "properties": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                        }
                    })
                
                return tools_data
                
    except Exception as e:
        print(f"   ❌ Error extracting tools: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"   Stack trace:\n{traceback.format_exc()}")
        return []

async def main():
    print("=" * 60)
    print("🚀 MCP Tool Extractor for Port")
    print("=" * 60)
    
    port_client_id = os.getenv("PORT_CLIENT_ID")
    port_client_secret = os.getenv("PORT_CLIENT_SECRET")
    
    if not port_client_id or not port_client_secret:
        print("❌ Missing required environment variables:")
        if not port_client_id:
            print("   - PORT_CLIENT_ID is not set")
        if not port_client_secret:
            print("   - PORT_CLIENT_SECRET is not set")
        sys.exit(1)
    
    print(f"✅ Environment variables loaded")
    print(f"   Client ID: {port_client_id[:8]}...")
    
    try:
        # Initialize Port client
        print(f"\n{'=' * 60}")
        print("Step 1: Initializing Port API Client")
        print("=" * 60)
        port_client = PortAPIClient(port_client_id, port_client_secret)
        
        # Get all MCP servers from Port
        print(f"\n{'=' * 60}")
        print("Step 2: Fetching MCP Servers from Port")
        print("=" * 60)
        mcp_servers = await port_client.get_all_mcp_servers()
        
        if not mcp_servers:
            print("\n⚠️  No MCP servers to process. Exiting.")
            return
        
        total_tools_synced = 0
        servers_processed = 0
        servers_skipped = 0
        servers_failed = 0
        
        # Process each MCP server
        print(f"\n{'=' * 60}")
        print("Step 3: Processing MCP Servers")
        print("=" * 60)
        
        for idx, server in enumerate(mcp_servers, 1):
            print(f"\n[{idx}/{len(mcp_servers)}] Processing MCP Server")
            print("-" * 60)
            
            server_id = server.get("identifier")
            server_title = server.get("title", server_id)
            command = server.get("properties", {}).get("command")
            
            print(f"   📦 Server: {server_title}")
            print(f"   🆔 Identifier: {server_id}")
            print(f"   💻 Command: {command or 'Not specified'}")
            
            if not command:
                print(f"   ⏭️  Skipping: no command specified")
                servers_skipped += 1
                continue
            
            # Extract tools from this MCP server
            try:
                tools = await extract_tools_from_mcp(command)
                
                if tools:
                    print(f"\n   📤 Syncing {len(tools)} tools to Port...")
                    
                    # Create tool entities in Port
                    for tool in tools:
                        await port_client.create_tool_entity(tool, server_id)
                    
                    # Update MCP server entity with list of tool names
                    tool_names = [tool["title"] for tool in tools]
                    await port_client.update_server_tools(server_id, tool_names)
                    
                    total_tools_synced += len(tools)
                    servers_processed += 1
                    print(f"   ✅ Successfully processed server: {server_title}")
                else:
                    print(f"   ⚠️  No tools found for server: {server_title}")
                    servers_skipped += 1
            except Exception as e:
                print(f"   ❌ Failed to process server: {server_title}")
                print(f"      Error: {type(e).__name__}: {str(e)}")
                servers_failed += 1
        
        # Final summary
        print(f"\n{'=' * 60}")
        print("🎉 Sync Complete - Summary")
        print("=" * 60)
        print(f"   Total servers found: {len(mcp_servers)}")
        print(f"   ✅ Successfully processed: {servers_processed}")
        print(f"   ⏭️  Skipped (no command): {servers_skipped}")
        print(f"   ❌ Failed: {servers_failed}")
        print(f"   📊 Total tools synced: {total_tools_synced}")
        print("=" * 60)
        
        if servers_failed > 0:
            sys.exit(1)
        
    except Exception as e:
        print(f"\n{'=' * 60}")
        print(f"❌ Fatal Error")
        print("=" * 60)
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        print(f"\nStack trace:\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
