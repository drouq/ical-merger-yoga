# Merged calendar

Takes a source iCal feed, adds the blocks in `blocks.csv`, publishes one .ics on GitHub Pages.
Rebuilds every 30 minutes (GitHub may run it late) and whenever you edit a file.

## One-time setup
1. Create a repo on github.com and upload all files, keeping the `.github/workflows` folder.
2. Settings > Secrets and variables > Actions > New repository secret:
   - `SOURCE_ICAL_URL` = your source feed URL
   - `OUTPUT_NAME` = a long random string, for example `k8f3a92xq71mzp04`
3. Settings > Pages > Source = GitHub Actions.
4. Actions tab > "Build merged calendar" > Run workflow.
5. Your feed URL is `https://<your-username>.github.io/<repo-name>/<OUTPUT_NAME>.ics`
6. Subscribe to that URL in your calendar app (use "From URL", not file import).

## Editing blocks
Edit `blocks.csv` on github.com. Save. The next run picks it up (a save triggers one at once).
End date is exclusive: nights of 10 and 11 Dec = start 2026-12-10, end 2026-12-12.

## Notes
- If the source feed is down, the build fails and the last good file stays online.
- Public repo: GitHub pauses scheduled runs after 60 days with no repo activity. Editing blocks.csv resets this.
- Pages URLs are public. The random OUTPUT_NAME is your only protection, so do not share the link.
