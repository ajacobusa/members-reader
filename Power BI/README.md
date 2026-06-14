# QuoteForge - Power BI package

This folder is an **open-and-refresh** Power BI deliverable. A binary `.pbix`
can't be authored safely outside Power BI Desktop, so instead you get the clean
data model, the DAX, and the exact report spec - about 10 minutes to a live
dashboard, and it refreshes from the CSVs forever after.

## Fastest path: open the PBIP scaffold
- Open **`PBIP/QuoteForge.pbip`** in Power BI Desktop (enable Preview features >
  *Power BI Project (.pbip) save option* + *TMDL* + *PBIR* if prompted). The
  star-schema tables, relationships and DAX measures are already wired to the
  CSVs. If the data moved, set the **DataFolder** parameter, then **Refresh**
  and add visuals per `model/DataModel.md`. It's a scaffold - on first open
  Power BI Desktop may ask to finalize the report layout.

## Or build from scratch (always works)
1. **Get Data > Folder** -> select this `Power BI/data` folder -> *Combine &
   Load* each CSV (or Get Data > Text/CSV per file for full control).
2. **Model view**: create the relationships listed in `model/DataModel.md`.
   Mark `dim_date` as the date table (`date` column).
3. **Measures**: New Measure -> paste each measure from `measures/Measures.dax`.
4. **Report**: build the four pages from `model/DataModel.md`. Save as
   `QuoteForge.pbix` in this folder.

## Refresh it later
- Re-run `python -m quoteforge.admin export-bi` to regenerate the CSVs from the
  latest orders, then hit **Refresh** in Power BI Desktop. No re-modelling.

## What's inside
- `PBIP/` - Power BI Project scaffold (TMDL model + relationships + measures)
- `data/` - star-schema CSV sources (facts + dims)
- `measures/Measures.dax` - ready-to-paste DAX
- `model/DataModel.md` - relationships + the 4-page report spec
- `QuoteForge_Executive_Presentation.pdf` / `.pptx` - the standalone exec deck
