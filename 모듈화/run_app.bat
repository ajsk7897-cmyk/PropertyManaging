@echo off
chcp 65001 > nul
echo =========================================
echo 🚀 모듈화된 부동산 자산관리 앱 실행 중...
echo =========================================
cd /d "%~dp0"
streamlit run app.py
pause
