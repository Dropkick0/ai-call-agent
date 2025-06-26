@echo off
echo Starting AI Cold Calls Demo Mode (Simple)...
echo.

REM Check if OpenAI API key is set
if "%OPENAI_API_KEY%"=="" (
    echo ERROR: OPENAI_API_KEY environment variable is not set.
    echo Please set it using: set OPENAI_API_KEY=your_api_key_here
    echo Or add it to your .env file
    pause
    exit /b 1
)

echo ✓ OpenAI API key found
echo.

REM Check if virtual environment exists and activate it
if exist "ai-cold-calls-env\Scripts\activate.bat" (
    echo Activating virtual environment...
    call ai-cold-calls-env\Scripts\activate.bat
    echo ✓ Virtual environment activated
    echo.
) else (
    echo No virtual environment found, using system Python...
)

REM Install demo mode dependencies if needed
echo Installing/checking demo mode dependencies...
python -m pip install --quiet sounddevice websockets structlog python-dotenv

echo ✓ Dependencies ready
echo.

echo Starting Demo Mode...
echo ====================================
echo You can now speak into your microphone
echo The AI agent will respond with voice
echo Press Ctrl+C to stop
echo ====================================
echo.

REM Run demo mode
python demo_mode.py

echo.
echo Demo ended.
pause 
