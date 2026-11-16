# Find a dermatologist near me

Page: `/find-a-dermatologist` (menu: **Find a dermatologist**), also reachable from every result page.

## What it does
1. You type your **city or town** (required), **district** (optional) and choose your **state or union territory**
   (all 28 states and 8 UTs).
2. It looks for skin clinics in the city (within 25 km of its centre). If none are listed, it looks in the
   district, then across the whole state, and tells you in a friendly sentence each time it widens the search.
3. Clinics are shown nearest first with their address and straight-line distance from the town centre.
4. A button always opens Google Maps with the search **"dermatologist in City, District, State"**.

## Buttons on each clinic
- **Call**: a `tel:` link to the clinic's first listed number, or a grey "Phone number not available".
- **Directions**: opens Google Maps directions to the clinic (`/maps/dir/?api=1&destination=LAT,LON`) in a new tab.
- **Book**: a short form (name, 10-digit mobile number, a date from today on, morning/afternoon/evening, optional
  note). It saves an **appointment request** in the `appointments` table with the clinic, the condition from the
  check (when the search started from a result) and the time. **The clinic is not contacted automatically**; the
  page says so and asks the person to call to confirm. Admins see all requests, newest first, at
  `/admin/appointments`. Deleting an account deletes its requests.

## Where the clinic list comes from
- **Default (free, no key): OpenStreetMap** via its Nominatim search service: places whose name contains "skin"
  and that are mapped as a clinic, doctor or hospital. Volunteer-made data, so small towns may have none.
  The Overpass API was tried first, but its public servers timed out (45 s+), so it is not used.
- **Optional: Google Places.** Put a key in `.env` as `GOOGLE_MAPS_API_KEY=...` (Google Cloud console → enable
  "Places API (New)" → create an API key; Google requires a billing account). Then the list comes from Google,
  which usually has more clinics and phone numbers. Keep the key private: `.env` is never committed.

## Privacy and fair use
Only the place names typed into the form are sent to these services, never anything about the person.
Results are cached in memory for a day and Nominatim requests are spaced 1 second apart, as its usage policy asks.
The page is limited to 30 searches per hour per visitor.
