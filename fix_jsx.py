lines = open('frontend/src/App.jsx', encoding='utf-8').readlines()
# Remove orphan lines 1491-1629 (0-indexed: 1490 to 1628)
# These are duplicate Factory Table + Insights + Top Recommendations outside of compare tab block
new_lines = lines[:1489] + lines[1629:]
open('frontend/src/App.jsx', 'w', encoding='utf-8').writelines(new_lines)
print(f'Done. Original: {len(lines)}, New: {len(new_lines)}')
