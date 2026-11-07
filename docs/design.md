# Financial Planner AI — UI Implementation Prompt

## Role and objective

Act as a senior product designer and frontend engineer. Implement a polished, production-quality AI financial-planning dashboard based on the reference image I provide with this prompt.

The application is a conversational financial planner. A user chats with an AI, uploads financial documents, reviews extracted information, approves what may be stored, and sees the financial dashboard update immediately as their data or goals change.

Reproduce the overall visual character of the reference—clean typography, generous spacing, rounded analytical cards, bright chart accents, readable financial data and refined motion—but follow every requirement below when the reference differs from this specification.

## Chat card catalogue

Every card the chat can draw, with sample data and a light/dark toggle, is in [chat-components.html](chat-components.html). Open it in a browser. Add a new card there first, then build its backend block in `backend/app/agent/blocks.py` and its frontend part in `frontend/components/blocks/`. Rules the page follows: one card per job, profit is teal and loss is rose, chart colours in fixed order, lucide icons only, no emoji.

## Critical layout correction

Do **not** build the thin icon-based navigation sidebar shown at the far left of the light-theme reference.

The desktop interface must have only two primary regions:

- **Left 40%:** AI conversation workspace.
- **Right 60%:** live financial dashboard.

The chat workspace itself begins at the left edge of the application. Do not add a third column, icon rail, global sidebar or duplicated navigation. A compact logo and theme control can sit in the chat header.

Use a resizable split-pane interaction if practical, with sensible limits of approximately 34%–46% for the chat panel. Default to 40%–60%.

## Technology and implementation approach

Use the existing project framework and design system. Do not replace established tooling merely to match this prompt.

If the project has no established frontend stack, use:

- React or Next.js with TypeScript.
- Tailwind CSS or well-structured CSS variables for styling.
- Recharts for charts, unless another chart library already exists.
- Framer Motion for state transitions, unless another motion library already exists.
- Lucide icons or the project’s existing icon set.

Create reusable components rather than putting the complete screen into one large component. Keep chart data, formatting helpers and animation configuration separate from presentation components.

## Visual direction

The product should feel like a calm, trustworthy financial cockpit—not a trading terminal, crypto dashboard or generic admin template.

Design characteristics:

- Modern editorial typography with a strong information hierarchy.
- Compact but breathable bento-grid composition on the dashboard.
- Rounded cards with consistent radii between 16px and 20px.
- Fine borders, subtle depth and restrained shadows.
- High information density without visual clutter.
- Tabular numerals for currency, percentages and time-series values.
- Indian currency formatting throughout, such as `₹5,00,000`, `₹48.5L` and `₹1.42Cr`.
- Gains use green with an upward arrow and plus sign.
- Losses use red with a downward arrow and minus sign.
- Warnings use amber with a warning icon.
- Never communicate meaning through color alone.

Avoid glassmorphism that reduces legibility, oversized gradients, excessive glow, neon cyberpunk styling, fake 3D objects and decorative charts without useful data.

## Design tokens

Implement the palette through semantic CSS variables so light and dark themes share the same component structure.

### Light theme

```css
--background: #F5F6F2;
--panel: #FFFFFF;
--panel-subtle: #F8FAF7;
--panel-elevated: #FFFFFF;
--text-primary: #111713;
--text-secondary: #647067;
--text-muted: #8C968F;
--border: #E2E7E1;
--border-strong: #CCD4CD;
--accent: #20C763;
--accent-bright: #BDF000;
--accent-soft: #E6F8EC;
--blue: #3478F6;
--orange: #FF6517;
--yellow: #FFBE0B;
--positive: #16A85A;
--negative: #EF3E46;
--negative-soft: #FDEBEC;
--warning: #E99A13;
--warning-soft: #FFF4DF;
--shadow-card: 0 8px 28px rgba(20, 32, 24, 0.06);
```

### Dark theme

```css
--background: #090C0A;
--panel: #151A17;
--panel-subtle: #111613;
--panel-elevated: #1B211D;
--text-primary: #F4F7F4;
--text-secondary: #AAB4AC;
--text-muted: #778078;
--border: #2B332D;
--border-strong: #3A443D;
--accent: #44E36F;
--accent-bright: #C8F500;
--accent-soft: #163D23;
--blue: #5686FF;
--orange: #FF6A32;
--yellow: #F8C62E;
--positive: #43DC76;
--negative: #FF535D;
--negative-soft: #442126;
--warning: #FFB83E;
--warning-soft: #3D3018;
--shadow-card: 0 12px 36px rgba(0, 0, 0, 0.28);
```

Use `Inter`, `Geist`, `SF Pro Display` or the project’s existing modern sans-serif. Use weights deliberately: 700 for primary totals, 600 for component titles, 400–500 for supporting information.

## Overall desktop structure

Fill the available viewport height and avoid whole-page scrolling when the display is sufficiently tall. The chat and dashboard regions may scroll independently.

### Left: AI conversation workspace

The chat panel occupies 40% of the width and includes:

1. **Compact header**
   - Mosaic logo and product name.
   - Small subtitle: `Your AI financial planner`.
   - Light/dark theme toggle.
   - Do not add navigation links or an icon sidebar.

2. **Conversation timeline**
   - User and assistant messages use visually distinct surfaces.
   - Keep bubbles wide enough for financial explanations and compact bullet lists.
   - Show small timestamps without allowing them to dominate.
   - Assistant answers may reference dashboard components, e.g. `Your cash flow is up 3.5% this month.`
   - When an answer references a dashboard card, hovering or focusing the referenced phrase should softly highlight that card on the right.

3. **Suggested prompts**
   - Examples: `Am I on track for retirement?`, `Review my portfolio risk`, `Plan for a home purchase` and `Show tax-saving opportunities`.
   - Render as compact full-width prompt rows or pills with a trailing arrow.

4. **Attachment and composer area**
   - Support multiple file chips for PDF, CSV, XLS/XLSX and common image formats.
   - Show upload progress, extraction status, success and failure states.
   - Composer placeholder: `Ask about your money…`.
   - Provide attach and send buttons with accessible labels.
   - Keep the composer sticky at the bottom of the chat panel.

5. **Human approval flow**
   - File extraction must first create a preview, never an implied automatic save.
   - Show a clear consent panel before storing structured financial information.
   - Let the user approve categories independently: income, expenses, investments, liabilities, goals and source documents.
   - Actions: `Save approved information` and `Keep only for this chat`.
   - Include the message: `Nothing is stored without your approval.`
   - Proposed changes should remain visually marked as `Draft` or `Pending approval` until confirmed.

### Right: live financial dashboard

The dashboard occupies 60% and uses a responsive bento grid. Its header contains:

- Title: `Financial overview`.
- One short supporting sentence.
- Month or date-range selector.
- `Updated just now` status after a live change.
- Optional overflow menu for dashboard preferences.

Do not place a separate navigation sidebar in this region.

## Dashboard components

### 1. Cash-flow trend card

This is the dominant card and spans the full dashboard width.

- Heading sentence: `Your cash flow is stronger this month — up by 3.5%.`
- Large, smooth line/area chart with an emerald line and subtle green fill.
- Use dotted or faint horizontal reference lines.
- Show month labels and properly formatted rupee values.
- Display a floating tooltip on hover/focus containing the month, value and percentage change.
- Include a compact `View details` action.
- Do not use a Sankey diagram here.

### 2. Income summary card

- Large current value, e.g. `₹5,00,000`.
- Month selector.
- Month-over-month change badge with arrow and explicit label.
- Simple source breakdown such as Salary and Freelance.
- Keep the breakdown typographic and minimal.

### 3. Expense summary card

- Large current value, e.g. `₹4,00,000`.
- Month selector.
- Month-over-month change badge.
- A rising expense is displayed as a negative condition unless context says otherwise.
- **Do not add category bars, segmented bars, progress bars or legends underneath this card.** The reference image’s lower expense bars are intentionally excluded.

### 4. Investment detail card

- Total investment value, e.g. `₹48.5L`.
- Performance delta compared with the previous month.
- A segmented horizontal distribution bar for Equity, Debt, Gold and Mutual Funds.
- Match every segment to a legend row containing category, rupee value and percentage.
- The sum of displayed percentages must always equal 100%.
- Green is used for the primary equity segment, blue for debt, orange for gold and yellow for mutual funds.

### 5. Holdings card

Create a compact, readable holdings table with these columns:

- Asset.
- Price.
- Weight.
- P/L.

Behaviour and styling:

- Use an available company or asset icon.
- When an icon is unavailable, show the asset’s first character in a colored circular avatar.
- Show the complete name below or beside the ticker.
- Use a miniature weight bar in the Weight column.
- Positive P/L uses green, an up arrow and a plus sign.
- Negative P/L uses red, a down arrow and a minus sign.
- Provide filters only if they add real value; avoid crowding the header.
- Include `View all` as a secondary action.

### 6. Risk-score card

- Semicircular gauge with green, lime, yellow, orange and red zones.
- Prominent score and verbal category, e.g. `6.8` and `Moderate`.
- Supporting metrics can include volatility, Sharpe ratio, maximum drawdown and diversification.
- Every metric needs a tooltip or accessible information label explaining it in plain language.

### 7. Goals card

- Show one or two priority goals with target amount, saved amount, target date and success status.
- Statuses are `On track`, `At risk` or `Off track`, with matching icon and text.
- A goal update made through chat initially appears as a draft.
- Include one compact progress visualization and a `View all` action.

## Responsive behaviour

### Large desktop: 1440px and above

- Maintain the 40%–60% split.
- Cash-flow card spans the dashboard width.
- Arrange summary cards and analytical cards in two or three columns depending on available space.

### Tablet and small desktop: 768px–1439px

- Allow a 38%–62% or 36%–64% split when necessary.
- Dashboard cards should collapse to two columns.
- Preserve usable chat width; do not compress message text excessively.

### Mobile: below 768px

- Do not keep a side-by-side split.
- Use two top-level tabs: `Chat` and `Overview`.
- Preserve chat state when switching tabs.
- Stack dashboard cards in order of decision importance: cash flow, income/expense, investments, holdings, risk and goals.
- Keep composer actions within thumb reach.

## Animation and interaction specification

Motion should make financial changes understandable. It must not feel playful or distracting.

### Page and card entrance

- On initial load, fade the shell in over 180–240ms.
- Stagger dashboard cards by approximately 35–50ms.
- Each card enters with opacity `0 → 1` and vertical offset `8px → 0`.
- Use a smooth ease such as `[0.22, 1, 0.36, 1]`.

### Cash-flow chart

- Draw the chart path from left to right over 700–900ms.
- Fade the area fill in after the path begins.
- Animate the active data-point marker with a restrained one-time pulse.
- Tooltips follow the pointer smoothly but must never lag enough to feel detached.
- When data changes, morph the existing path into the new path instead of replacing the entire chart.
- Keep the previous path briefly visible as a low-opacity dotted line for 600–900ms when a comparison adds meaning.

### Investment distribution bar

- Animate segments from zero width to their final proportional widths.
- Use one continuous 550–750ms sequence rather than separate bouncing segments.
- When allocation changes, animate segment boundaries smoothly.
- Briefly highlight the changed legend row.

### Financial values

- Count numeric totals from their previous value to their new value over 400–650ms.
- Preserve proper Indian digit grouping during animation.
- Never animate from zero when updating existing data; start from the prior displayed value.
- Pair changed numbers with a temporary directional indicator.

### Holdings

- Reorder rows using layout animation when sorting or when weights change.
- Animate weight bars horizontally.
- Newly added holdings fade and slide in gently.
- Loss transitions use a restrained red background flash that fades quickly; do not shake the interface.

### Chat-to-dashboard updates

- When the AI proposes a new goal or financial change, add a `Draft` card on the dashboard with a soft amber outline.
- Connect the assistant message to the affected card through synchronized highlighting, not a permanent drawn line.
- After approval, transition the card from amber draft styling to its normal state.
- Update affected charts, totals and statuses together in one coordinated 500–900ms sequence.
- Show `Updated just now` after the transition completes.
- If the user rejects the proposal, return the dashboard to the previous state without persisting the draft.

### Hover and focus states

- Cards lift no more than 2px and strengthen their border slightly.
- Rows and buttons use subtle surface changes rather than dramatic scaling.
- All hover states must have equivalent keyboard-focus states.

### Reduced motion

Respect `prefers-reduced-motion`.

- Disable path drawing, count-up effects, pulsing and large translations.
- Replace them with short opacity transitions or immediate state updates.

## Data and state requirements

Use a coherent typed state model so all cards derive from the same financial data rather than unrelated hard-coded values.

At minimum, model:

- Income sources and monthly totals.
- Expense totals.
- Cash-flow history.
- Investment categories and allocation percentages.
- Holdings with current price, weight and profit/loss.
- Risk metrics.
- Goals with target, current amount, target date and status.
- Uploaded documents.
- Proposed changes and approval status.
- Current theme and selected period.

Changing a value through the demo chat must update every dependent component consistently. For example, adding a monthly expense should reduce cash flow and may affect goal status. Do not produce contradictory totals.

If no backend is connected, create realistic mock data and local interactive state. Clearly isolate the mock-data layer so it can later be replaced by API responses.

## Accessibility and quality requirements

- Meet WCAG AA color contrast for text and interactive controls.
- Use semantic landmarks, headings, buttons and tables.
- Provide keyboard navigation for chart points, date selectors, chat actions and approval controls.
- Add screen-reader summaries for charts instead of relying solely on SVG visuals.
- Use `aria-live="polite"` for completed financial updates and approval results.
- Do not expose sensitive financial details in unnecessary browser logs.
- Format currency and percentages with reusable locale-aware utilities.
- Include loading, empty, partial-data, error, offline and permission-denied states.
- Avoid layout shift while charts or fonts load.

## Suggested component architecture

```text
FinancialPlannerShell
├── ChatWorkspace
│   ├── ChatHeader
│   ├── MessageTimeline
│   ├── SuggestedPrompts
│   ├── UploadQueue
│   ├── StorageConsentPanel
│   └── ChatComposer
└── FinancialDashboard
    ├── DashboardHeader
    ├── CashFlowTrendCard
    ├── IncomeSummaryCard
    ├── ExpenseSummaryCard
    ├── InvestmentDetailCard
    ├── HoldingsCard
    ├── RiskScoreCard
    └── GoalsCard
```

Do not treat this tree as a requirement to create excessive one-line components. Split components where ownership, reuse, testing or performance makes the boundary useful.

## Acceptance checklist

The implementation is complete only when:

- There is no thin navigation sidebar or icon rail.
- Chat occupies approximately 40% and the live dashboard approximately 60% on desktop.
- Light and dark themes use semantic tokens and both feel intentionally designed.
- The cash-flow card is the dashboard’s primary visual component.
- Income and Expense cards are simple; the Expense card has no lower category bars.
- Investment distribution uses an animated segmented bar and totals 100%.
- Holdings use real icons when available and first-letter avatars as a fallback.
- Gains, losses and warnings are understandable without relying only on color.
- Chat-driven draft changes require user approval before simulated persistence.
- Relevant dashboard components update together with restrained animation.
- Mobile uses Chat and Overview tabs rather than squeezing the desktop split.
- Keyboard navigation, reduced motion and chart summaries are implemented.
- The page is visually polished at common desktop, tablet and mobile sizes.

## Final delivery expectations

Implement the complete responsive screen, not a static image. Use realistic mock data, functional theme switching, working date controls, chart tooltips, suggested prompts, file-upload states, consent interactions and at least one demonstrable chat-driven dashboard update.

After implementation:

1. Run the project’s formatter, linter, type checker and relevant tests.
2. Verify the layout at desktop, tablet and mobile widths.
3. Check both themes for contrast and overflow.
4. Verify that reduced-motion mode works.
5. Summarize the components created, interactions implemented and any assumptions made.
