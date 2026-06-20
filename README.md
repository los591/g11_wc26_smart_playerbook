# WC 2026 Smart Playerbook ⚽

A live digital companion for the 2026 FIFA World Cup — think Panini album, but it updates itself.

🔗 **[Live app → g11-wc-2026.streamlit.app](https://g11-wc-2026.streamlit.app/)**

---

## What it is

Player profiles and live match statistics for all 1,247 players across 48 national teams at the 2026 FIFA World Cup (USA · Canada · México).

Stats refresh automatically every 6 hours throughout the tournament.

## Features

- **Player profiles** — photo, bio, club, position, and live WC match statistics
- **Group Standings** — derived from live match data, updated every 6h
- **Player Leaderboard** — goals, assists, minutes, rating, cards, saves
- **Match Calendar** — all fixtures with scores/kickoff times in your local timezone
- **Player Comparison** — side-by-side WC stats for any two players
- **Pre-WC Leagues** — 2025/26 club season stats for context
- **Search** — find any player by name or club across all 48 squads

## Tech stack

- [Streamlit](https://streamlit.io/) — app framework
- [API-Football](https://www.api-football.com/) via RapidAPI — live match data
- [GitHub Actions](https://github.com/features/actions) — automated 6h data refresh
- Python · JSON · REST APIs

## Data

Player and fixture data lives in a private companion repository and is fetched at runtime via the GitHub API. The dataset covers all 1,247 players including pre-tournament injury replacements.

## Contact

Questions, research inquiries, or just want to talk soccer?
📧 Los0636@gmail.com
