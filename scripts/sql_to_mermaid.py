"""Throwaway: dump a CREATE TABLE script as a Mermaid ER diagram.

Usage: python scripts/sql_to_mermaid.py docs/01_schema.sql > docs/01_schema.md
"""

import re
import sys

sql = open(sys.argv[1]).read()
skip = ("CONSTRAINT", "PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN KEY", "REFERENCES", "ON", "--")

print("```mermaid\nerDiagram")
for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
    print(f"  {table} {{")
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith(skip) and (m := re.match(r"(\w+)\s+(\w+)", line)):
            print(f"    {m[2]} {m[1]}")
    print("  }")
    for parent in re.findall(r"REFERENCES (\w+)", body):
        print(f'  {parent} ||--o{{ {table} : ""')
print("```")
