# Batch Scripts for Recursive PPT to PNG Conversion

This package includes three batch scripts for Windows to recursively convert all PPT files in a folder structure.

## Scripts Overview

### 1. `convert_all_ppt.bat` - Simple Recursive Conversion
Converts all `.ppt` files in a folder and its subfolders, placing PNG files next to the original PPT files.

**Usage:**
```batch
REM Convert all PPT files in current directory
convert_all_ppt.bat

REM Convert all PPT files in specific folder
convert_all_ppt.bat "C:\path\to\folder"
```

**Features:**
- ✅ Recursively searches all subfolders
- ✅ Creates PNG files in same location as PPT files
- ✅ Shows progress counter
- ✅ Reports success/failure statistics

---

### 2. `convert_all_ppt_advanced.bat` - With Custom Flags
Same as above but allows passing `--no-tiling` and `--no-crop` flags.

**Usage:**
```batch
REM Convert with default settings
convert_all_ppt_advanced.bat "C:\path\to\folder"

REM Convert without tiling
convert_all_ppt_advanced.bat "C:\path\to\folder" --no-tiling

REM Convert without cropping
convert_all_ppt_advanced.bat "C:\path\to\folder" --no-crop

REM Convert with both flags
convert_all_ppt_advanced.bat "C:\path\to\folder" --no-tiling --no-crop

REM Use current directory with flags
convert_all_ppt_advanced.bat --no-tiling --no-crop
```

**Features:**
- ✅ All features from simple version
- ✅ Support for `--no-tiling` flag
- ✅ Support for `--no-crop` flag
- ✅ Flexible argument order

---

### 3. `convert_all_ppt_organized.bat` - Organized Output
Converts all PPT files and saves PNG output to a separate folder while preserving the folder structure.

**Usage:**
```batch
REM Convert and save to default "png_output" folder
convert_all_ppt_organized.bat

REM Specify source folder (output goes to "png_output")
convert_all_ppt_organized.bat "C:\path\to\source"

REM Specify both source and output folders
convert_all_ppt_organized.bat "C:\path\to\source" "C:\path\to\output"
```

**Example:**
```
Source:
  textures/
    characters/
      hero.ppt
      villain.ppt
    items/
      sword.ppt

Output (png_output/):
  characters/
    hero.png
    villain.png
  items/
    sword.png
```

**Features:**
- ✅ Preserves folder structure
- ✅ Organizes all PNG files in separate output folder
- ✅ Automatically creates output directories
- ✅ Keeps original PPT files untouched
- ✅ Clean separation of source and output

---

## Requirements

- Python 3.7 or higher installed and in PATH
- All dependencies from `requirements.txt` installed:
  ```batch
  pip install -r requirements.txt
  ```
- `ppt_to_png.py` must be in the same directory as the batch files OR in your system PATH

## Output

All scripts display:
- Progress counter for each file
- Success/failure status for each conversion
- Final statistics (total, successful, failed)

Example:
```
=========================================
PPT to PNG Recursive Converter
=========================================
Processing folder: C:\textures

[1] Converting: C:\textures\hero.ppt
    SUCCESS

[2] Converting: C:\textures\items\sword.ppt
    SUCCESS

=========================================
Conversion Complete
=========================================
Total files processed: 2
Successful: 2
Failed: 0
=========================================
```

## Tips

1. **Test first**: Run on a small folder first to verify settings
2. **Backup**: Keep backups of original PPT files
3. **Large batches**: For thousands of files, consider running overnight
4. **Error checking**: Review failed conversions in the output log

## Troubleshooting

**Script doesn't find Python:**
- Ensure Python is installed and added to PATH
- Try using full path: `"C:\Python\python.exe" ppt_to_png.py`

**Permission errors:**
- Run batch file as Administrator
- Check folder permissions

**No files found:**
- Verify folder path is correct
- Ensure files have `.ppt` extension (case-sensitive on some systems)
