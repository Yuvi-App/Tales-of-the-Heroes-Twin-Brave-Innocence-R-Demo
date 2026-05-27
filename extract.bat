@echo off
echo Make sure the ISO is at the root of the repo and is named TB_InnoR_Demo.iso
uv run tb-tools extract --iso TB_InnoR_Demo.iso
pause