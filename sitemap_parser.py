import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote

def parse_sitemap_to_tree(xml_file):
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except FileNotFoundError:
        print(f"Error: {xml_file} not found. Please ensure it's in the same directory.")
        return {}

    urls = [elem.text for elem in root.findall('ns:url/ns:loc', namespace)]
    url_tree = {}

    for url in urls:
        parsed_url = urlparse(unquote(url))
        domain = parsed_url.netloc
        path_parts = [p for p in parsed_url.path.split('/') if p]
        
        current_level = url_tree
        
        if domain not in current_level:
            current_level[domain] = {}
        current_level = current_level[domain]
        
        for part in path_parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
            
        if parsed_url.query:
            query_str = f"?{parsed_url.query}"
            if query_str not in current_level:
                current_level[query_str] = {}
            current_level = current_level[query_str]
            
        # NEW: Store the full URL at this final node level
        current_level['__url__'] = url

    return url_tree

def print_tree(d, indent=""):
    """Recursively prints the dictionary in a CLI-style tree format with full URLs."""
    # Filter out our special '__url__' key so it doesn't print as a regular branch
    keys = [k for k in d.keys() if k != '__url__']
    
    for i, key in enumerate(keys):
        is_last = (i == len(keys) - 1)
        connector = "└── " if is_last else "├── "
        
        child = d[key]
        
        # NEW: Check if this node has a full URL attached to it
        url_display = ""
        if isinstance(child, dict) and '__url__' in child:
            url_display = f"  --->  {child['__url__']}"
        
        # Print the branch name and the URL next to it
        print(f"{indent}{connector}{key}{url_display}")
        
        # Adjust the indentation for the next level and recurse
        new_indent = indent + ("    " if is_last else "│   ")
        if isinstance(child, dict):
            print_tree(child, new_indent)

if __name__ == "__main__":
    file_name = 'sitemap.xml'
    print(f"Parsing {file_name}...\n")
    
    sitemap_tree = parse_sitemap_to_tree(file_name)
    
    if sitemap_tree:
        # Print the root domain first if it has a base URL
        # For this script, we'll just print the visual tree directly
        print_tree(sitemap_tree)