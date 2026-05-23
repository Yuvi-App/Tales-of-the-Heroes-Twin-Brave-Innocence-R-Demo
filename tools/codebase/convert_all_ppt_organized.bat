@echo off
REM Batch script to recursively convert all PPT files to PNG
REM and organize output in a separate folder with preserved structure
REM Usage: convert_all_ppt_organized.bat [source_folder] [output_folder]

setlocal enabledelayedexpansion

REM Set default folders
set "SOURCE_FOLDER=%cd%"
set "OUTPUT_FOLDER=%cd%\png_output"

REM Parse arguments
if not "%~1"=="" set "SOURCE_FOLDER=%~1"
if not "%~2"=="" set "OUTPUT_FOLDER=%~2"

echo =========================================
echo PPT to PNG Recursive Converter (Organized)
echo =========================================
echo Source folder: %SOURCE_FOLDER%
echo Output folder: %OUTPUT_FOLDER%
echo.

REM Create output folder if it doesn't exist
if not exist "%OUTPUT_FOLDER%" (
    mkdir "%OUTPUT_FOLDER%"
    echo Created output folder: %OUTPUT_FOLDER%
    echo.
)

REM Counter for tracking progress
set /a count=0
set /a success=0
set /a failed=0

REM Recursively find all .ppt files
for /r "%SOURCE_FOLDER%" %%f in (*.ppt) do (
    set /a count+=1
    
    REM Get the relative path from source folder
    set "FULL_PATH=%%~dpf"
    set "REL_PATH=!FULL_PATH:%SOURCE_FOLDER%=!"
    
    REM Create corresponding directory in output folder
    set "OUT_DIR=%OUTPUT_FOLDER%!REL_PATH!"
    if not exist "!OUT_DIR!" mkdir "!OUT_DIR!"
    
    REM Get filename without extension
    set "FILENAME=%%~nf"
    
    REM Set output file path
    set "OUT_FILE=!OUT_DIR!!FILENAME!.png"
    
    echo [!count!] Converting: %%f
    echo     Output: !OUT_FILE!
    
    REM Run the Python script
    python ppt_to_png.py "%%f" "!OUT_FILE!"
    
    REM Check if conversion was successful
    if !errorlevel! equ 0 (
        set /a success+=1
        echo     SUCCESS
    ) else (
        set /a failed+=1
        echo     FAILED
    )
    echo.
)

echo =========================================
echo Conversion Complete
echo =========================================
echo Total files processed: !count!
echo Successful: !success!
echo Failed: !failed!
echo Output location: %OUTPUT_FOLDER%
echo =========================================

pause
