# Add Properties To `properties.html`

Use this workflow whenever the user provides a list of property addresses to add to the closed properties page.

## Goal

Add new property tiles to `properties.html` by copying an existing tile, editing the details, and placing the new tiles at the beginning of the properties grid unless the user says otherwise.

## Input Expected From User

The user will usually only provide property addresses, for example:

- `2172 Barnes Wharf Ln, Alameda, CA 94501`
- `1511 Goodman Ave, Redondo Beach, CA 90278`

## Required Workflow

1. Open `properties.html`.
2. Find the first property tile inside `.properties-grid`.
3. Copy that full tile block exactly.
4. Paste the new tile at the beginning of the grid.
5. Edit only the property-specific values:
   - Zillow URL
   - image file path
   - image `alt`
   - address line
   - city / state / ZIP line
   - sale price
   - cashback badge
   - cashback stat

## Zillow Lookup Rules

For each address:

1. Find the Zillow property page.
2. Pull the relevant details from Zillow.
3. Prefer a sold price if Zillow shows a sold event.
4. If Zillow does **not** show the property as sold, flag that clearly and use the current Zillow price only if the user still wants it added.
5. Also pull a usable Zillow image and save it into `assets/images/`.

## Sale / Listing Details To Capture

At minimum capture:

- full Zillow URL
- price used for the tile
- whether that price is sold price or current listing price
- sold date if available
- beds / baths / sqft for verification

## Commission And Cashback Rules

The page should follow the cashback calculator logic from `index.html`.

### Seller Paid Commission

Seller commission is always:

- `sale_price * 0.025`

### Our Fee

Use the calculator logic in `index.html`:

- Base fee: `$6,895`
- If purchase price is above `$1,000,000`, add `$100` for each `$100,000` over `$1,000,000`
- Round that extra amount using the same logic as the calculator:
  - use `Math.ceil((purchasePrice - 1000000) / 100000) * 100`
- Cap total fee at `$7,895`

Equivalent formula:

```text
if price <= 1,000,000:
    fee = 6,895
else:
    fee = min(6,895 + ceil((price - 1,000,000) / 100,000) * 100, 7,895)
```

### Cashback

```text
cashback = (sale_price * 0.025) - our_fee
```

## Display Formatting Rules

- Match the existing tile style exactly.
- Round displayed sale price the same way existing tiles do:
  - `$910K`
  - `$1.45M`
  - `$1.54M`
- Round displayed cashback similar to the current page:
  - `~$17k`
  - `~$29k`
  - `~$31k`
- Use the same cashback value in both places:
  - badge text
  - cashback stat

## Image Rules

- Download a Zillow image for the property.
- Save it in `assets/images/`.
- Use a descriptive lowercase hyphenated filename, for example:
  - `1511-goodman-ave-redondo-beach-960x720.jpg`
- Do not change existing images for other tiles.

## HTML Editing Rules

- Do not redesign the tile.
- Do not convert the page to dynamic JavaScript.
- Do not change unrelated parts of `properties.html`.
- Keep the inserted tile markup structurally identical to the copied tile.

## If A Property Is Not Clearly Sold

If Zillow shows the property as active, new construction, pending, or otherwise not clearly sold:

- note that clearly in the response
- state what price was used
- do not describe it as sold unless Zillow shows that

## Final Response Checklist

After editing, report:

- which properties were added
- the Zillow links used
- the price used for each property
- seller commission for each property
- our fee for each property
- cashback for each property
- whether any property was not actually sold on Zillow

## Important Files

- `properties.html`
- `index.html`
- `assets/images/`
