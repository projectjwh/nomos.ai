# Design System Specification: High-End Digital Editorial

## 1. Overview & Creative North Star
**Creative North Star: The Ethereal Gallery**

This design system is not a set of templates; it is a philosophy of restraint. We move beyond "Apple-inspired" by leaning into a high-end editorial experience that treats every screen as a curated gallery space. The goal is to create a digital environment that feels breathable, expensive, and laser-focused.

We break the "standard web look" by eschewing rigid borders and boxy layouts. Instead, we use **Intentional Asymmetry** and **Tonal Depth** to guide the eye. By utilizing generous whitespace (the "Luxury Gap") and overlapping glass layers, we create a sense of physical space and sophistication that feels tactile yet digital-first.

---

## 2. Colors & Surface Philosophy

Our palette is anchored in monochromatic precision, using vibrant accents only to signal intent or success.

### The "No-Line" Rule
**Explicit Instruction:** 1px solid borders are strictly prohibited for sectioning. 
Structure must be defined through **Background Color Shifts** or **Tonal Transitions**. To separate the navigation from the hero, or a card from the background, use a shift from `surface` to `surface-container-low`. The transition should be felt, not seen.

### Surface Hierarchy & Nesting
Treat the UI as a series of stacked, premium materials.
- **Base Layer:** `surface` (#f9f9fb)
- **Secondary Sectioning:** `surface-container-low` (#f3f3f5)
- **Primary Content Cards:** `surface-container-lowest` (#ffffff) for maximum "pop."
- **Interactive/Raised Elements:** `surface-container-high` (#e8e8ea)

### The "Glass & Gradient" Rule
To achieve a signature high-end feel:
- **Glassmorphism:** Use `surface_container_lowest` at 70% opacity with a `backdrop-filter: blur(20px)` for floating navigation and modals.
- **Signature Textures:** For primary CTAs, do not use flat hex codes. Apply a subtle linear gradient from `primary` (#004e9f) to `primary_container` (#0066cc) at a 135-degree angle to add "soul" and depth.

---

## 3. Typography: The Editorial Voice

We use **Inter** (as the high-performance alternative to San Francisco) to drive a clear, authoritative hierarchy.

*   **Display (lg/md/sm):** Use for hero moments. Set with tight letter-spacing (-0.02em) and `on_surface` color. These should feel like magazine headlines.
*   **Headline (lg/md/sm):** Use for section headers. Maintain significant whitespace above headlines to announce a change in context.
*   **Title (lg/md/sm):** Used for card headings and navigational elements. Always high-contrast.
*   **Body (lg/md):** Our workhorse. Use `on_surface_variant` (#414753) for long-form text to reduce eye strain and increase the "premium" feel.
*   **Labels:** Use `label-md` in uppercase with +0.05em letter spacing for small metadata or categories to create an "archival" look.

---

## 4. Elevation & Depth: Tonal Layering

We do not use shadows to create "pop"; we use them to simulate "ambient light."

*   **The Layering Principle:** Place a `surface-container-lowest` card on a `surface-container-low` background. The contrast in lightness creates a natural lift without a single pixel of shadow.
*   **Ambient Shadows:** For floating elements (Modals/Popovers), use a multi-layered shadow: `0px 10px 40px rgba(26, 28, 29, 0.06)`. The color is a tinted version of `on_surface`, never pure black.
*   **The "Ghost Border" Fallback:** If a border is required for accessibility, use `outline_variant` at **15% opacity**. It should be a whisper, not a statement.
*   **Depth through Blur:** Use `backdrop-filter: blur(12px)` on all overlays to allow the brand colors and imagery to bleed through, ensuring the UI feels integrated into the content.

---

## 5. Components

### Buttons
- **Primary:** Gradient fill (`primary` to `primary_container`), `on_primary` text, `xl` (1.5rem) corner radius.
- **Secondary:** `surface_container_high` fill, no border, `on_surface` text.
- **Tertiary:** No background. `primary` text with an underline that appears only on hover.

### Cards & Lists
- **The Rule:** No dividers. Separate list items using `body-md` padding (1rem) and subtle background shifts (`surface-container-low`) on hover.
- **Cards:** Use `xl` (1.5rem) corner radius. Content should have generous internal padding (at least 24px-32px).

### Input Fields
- **State:** Defaults to `surface_container_low`. On focus, transitions to `surface_container_lowest` with a `Ghost Border` of `primary` at 40% opacity.
- **Shape:** `md` (0.75rem) corner radius for a modern, approachable feel.

### Selection Controls (Chips/Radios)
- **Selection Chips:** Use `secondary_fixed` for unselected and `primary` for selected. Avoid heavy outlines; use color fills to indicate state.

---

## 6. Do’s and Don’ts

### Do
- **Do** use "The Luxury Gap." If you think there is enough whitespace, add 20% more.
- **Do** use `surface_tint` sparingly to draw attention to active states or progress.
- **Do** ensure all high-resolution imagery uses a subtle `md` or `lg` corner radius to match the UI container language.

### Don’t
- **Don't** use pure black (#000000) for text. Use `on_surface` (#1a1c1d) to maintain a soft, premium high-contrast look.
- **Don't** stack more than three levels of surface depth (Base > Container > Card). Any more creates visual clutter.
- **Don't** use standard "Drop Shadows." If an element needs to feel elevated, use tonal shifting or the Ambient Shadow specification defined in Section 4.
- **Don't** use dividers or lines to separate content blocks. Use the Spacing Scale.