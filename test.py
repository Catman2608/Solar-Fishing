import subprocess

# Query non-background processes for their window names
scr = 'tell app "System Events" to get name of windows of (every process whose background only is false)'
res = subprocess.run(['osascript', '-e', scr], capture_output=True, text=True)
print(res.stdout.strip())
