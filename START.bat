@echo off
title Instagram Scraper
color 0A

echo ====================================================
echo      Instagram Scraper (Brands ^& Influencers)
echo ====================================================
echo.

set /p MODE="Scrape Brands or Influencers? (B/I): "
if /i "%MODE%"=="B" (
    set SCRAPE_MODE=brands
) else if /i "%MODE%"=="I" (
    set SCRAPE_MODE=influencers
) else (
    echo Invalid choice. Defaulting to Brands.
    set SCRAPE_MODE=brands
)

echo.
set /p HASHTAGS="Enter hashtags separated by spaces (e.g., fashion shoes realestate): "
if "%HASHTAGS%"=="" set HASHTAGS=fashion

set /p FOLLOWERS="What is the MINIMUM follower count? (Just press Enter for 20000): "
if "%FOLLOWERS%"=="" set FOLLOWERS=20000

set /p MAX_PROFILES="How many FULLY VALID profiles do you want it to scrape/DM in total per hashtag? (e.g. 50): "
if "%MAX_PROFILES%"=="" set MAX_PROFILES=20

echo.
echo ----------------------------------------------------
echo Mode     : %SCRAPE_MODE%
echo Hashtags : %HASHTAGS%
echo Followers: %FOLLOWERS%
echo Target   : %MAX_PROFILES% profiles
echo Please do not close this window until it finishes.
echo ----------------------------------------------------
echo.

python main.py --mode %SCRAPE_MODE% --hashtags %HASHTAGS% --min-followers %FOLLOWERS% --max-per-hashtag %MAX_PROFILES%

echo.
echo ----------------------------------------------------
echo Scraping Finished! Check the data folder for results.
echo ----------------------------------------------------
pause
