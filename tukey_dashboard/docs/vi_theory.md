# VI course theory (UPC, Information Visualization, Pere-Pau Vázquez, ViRVIG): what to apply and cite

Extracted from every page of the 8 lecture decks, the VOTD PDFs, the Project 1 statement, and the student's earlier project.
Content marked **(general, not in slides)** comes from general knowledge, not from the course material.

## Deck abbreviations (cite as `deck p.N` = PDF page N)

| Abbr | File (`C:\Users\matia\Documents\VI\PROJECT\...`) | Topic |
|---|---|---|
| **W1** | `class_notes\Week1_IntroVis (4).pdf` (135 p) | Intro: definition, Anscombe, takeaways, history |
| **W2** | `class_notes\Week2_IntroVis_2 (4).pdf` (85 p) | General rules, data types, Shneiderman tasks, nested model, pipeline, Mantra, "where is the trick" |
| **W3** | `class_notes\Week3_VisualizationTechniquesReduced (5).pdf` (137 p) | Chart catalogue: quantities, distributions, proportions, relationships, time series, maps |
| **P1** | `class_notes\IV_Perception (3).pdf` (114 p) | Preattentive processing, memory model, Gestalt laws |
| **P2** | `class_notes\IV_PerceptionPart2 (3).pdf` (85 p) | Applying perception: channel rankings, Weber/Stevens, dual axes, lie factor, data-ink |
| **CB** | `class_notes\Colorblindness (5).pdf` (16 p) | Visualization for colorblind people |
| **MV** | `class_notes\IV_MultipleViews.pdf` (133 p) | Multiple/coordinated views, data reduction, focus+context |
| **AV** | `class_notes\AdvancedVisualizationTechniques.pdf` (76 p) | Sankey, horizon, hierarchies, networks, UpSet, uncertainty, multi-functioning elements |
| **PR** | `Project1 (1).pdf` (4 p) | Project 1 statement and grading checklist |

Authors cited in the slides: Munzner (definition, nested model, channel ranking, facet matrix), Mackinlay (1986 effectiveness quote, 1987 ranking table, 2000 data examples), Card 2008 (expressiveness quote), Shneiderman 1996 (tasks, data types, Mantra), Ware 2001/2012/2013 (preattentive, texture, integral/separable), Healey (preattentive demos), Garner 1974, Palmer & Rock 1994, Slocum 1983, Weber, Stevens, Flannery, Tufte 1983/2001 (lie factor, data-ink), Few 2006, Bertin (quote), Anscombe 1973, Cairo (Datasaurus), Cleveland & McGill plus Heer & Bostock CHI 2010, Kosara 2016 (donuts), Wilke (clauswilke.com/dataviz), Aigner 2011 (pipeline), Cockburn (survey), Lamping 1995, Sun et al. 2022 (cross-view links), Padilla, Kay & Hullman (uncertainty), Henry & Fekete 06, Datawrapper blog (colorblindness).
**Not in any slide:** Baldonado's rules, the word "rainbow", "diverging colormap", Bertin's retinal variables, and Munzner's "what-why-how" as a phrase.

---

## 1. Rules checklist (52 rules)

Format: **rule** · source · *course term*.

### Purpose, honesty, audience
1. **Build the vis for a task.** Show the data so people can carry out tasks more effectively, and augment the human instead of replacing them. · W1 p6, p60 · *Munzner's definition*
2. **Do not use vis if the answer is just a calculation.** "If you know what you are looking for, you probably do not need the visualization." · W1 p63 · *when (not) to visualize*
3. **Show the data, not only summaries.** Summaries lose information; use vis to confirm expected and find unexpected patterns and to assess a statistical model. Anscombe: "make both calculations and graphs." · W1 p66-70; Datasaurus W1 p73 · *Anscombe's quartet*
4. **Encode exactly the data relations intended, nothing more and nothing less.** · W1 p20; P2 p33 (Card 2008) · *expressiveness*
5. **Pick the encoding that best fits human perception and the task.** · W1 p20; P2 p34 (Mackinlay 1986) · *effectiveness*
6. **Make the design reflect its intent and serve the user's tasks.** This is a cost-value ratio in time and screen space. · W1 p20; P2 p38 · *appropriateness*
7. **Be honest.** Check the data: is it correct, up to date, how was it collected, is anything missing? · W2 p3 · *General rules: be honest*
8. **Above all, show the data.** Avoid non-informative elements and make sure every encoding is perceivable by everybody. · W2 p3 · *show the data*
9. **Explain your encodings and label your axes.** · W2 p4 · *General rules*
10. **Make the geometry change as the data changes.** Distortion leads to disinformation. · W2 p4 · *General rules*
11. **Take the audience into account.** Consider color blindness, data literacy, screen size, and expert vs general public. · W2 p5 · *General rules*
12. **Tell a story and give a message.** "Do you have a takeaway message? Write it." · W2 p5 · *General rules*
13. **Make the graph complete.** Label all axes, give it a title, and for an explanatory vis put the takeaway in the title. · P2 p70 · *complete graph*
14. **Let the decision-maker manipulate the graphic.** Bertin: "The best graphic operations are those carried out by the decision-maker themself." · W1 p78 · *Bertin quote*

### Perception and channels
15. **Encode the most important attribute with the highest-ranked channel.** · P2 p35-37 (Munzner); P2 p9 · *effectiveness principle*
16. **Match the channel type to the data type.** Use magnitude channels for ordered data and identity channels for categorical data. · P2 p35-36 · *expressiveness principle*
17. **Prefer position on a common scale, then length; avoid angle, area and volume for precise comparison.** · P2 p35, p39, p60 · *channel ranking; Cleveland & McGill / Heer & Bostock*
18. **Use preattentive features for what must pop out:** color (hue, lightness), elementary shape (size, elongation, orientation), motion and spatial grouping. · P1 p44-58, p72 (Ware 2013) · *pop-out / preattentive processing (< 200-250 ms)*
19. **Never make a target depend on a conjunction of two features.** That forces a serial search. · P1 p54, p59-60 · *conjunction search*
20. **Remember preattentive features are asymmetric, and control background distractors.** · P1 p60 · *preattentive tips*
21. **Highlight one item in a hue and leave the rest grey.** Show the focus series in color over grey context (password bars, Brazil vs world fertility). · P1 p61-64 · *pop-out highlight*
22. **Avoid gratuitous motion and flicker.** "Movement ALWAYS attracts our attention." · P1 p65 · *motion*
23. **Design for limited working memory** (3-4 chunks, a few seconds). Use preattentive features as much as possible. · P1 p41, p43 · *3-stage memory model*
24. **Group with Gestalt laws:** proximity, similarity, continuity, common fate, parallelism, connectedness, symmetry, common region, closure, Prägnanz, figure/ground, focal point. · P1 p78-95 · *perception laws / Gestalt*
25. **Use connectedness for strong grouping.** It can beat proximity, color, size and shape (Palmer & Rock 1994). · P1 p88 · *connectedness*
26. **Give the view one entry point.** · P1 p95 · *principle of focal point*
27. **Organize the layout from large to small and keep structure at each level.** · P2 p9 · *feature hierarchy / visual search*
28. **Use integral dimensions for holistic reading and separable ones for analytic reading.** · P2 p17-22 (Garner 1974; Ware 2012) · *integral vs separable dimensions*
29. **Add references (alignment, gridlines, a top line) to improve relative judgments.** Just noticeable difference ∝ the stimulus. · P2 p45-49 · *Weber's law / relative judgments*
30. **Do not encode a precise quantity in area or volume.** Perceived magnitude follows a power law, and larger dimension means more underestimation. · P2 p50-53, p61 · *Stevens' law; Flannery's compensation*

### Honesty of scales
31. **Keep the lie factor near 1.** · P2 p62-65 (Tufte 1983; fuel economy example: lie factor 14.8) · *lie factor = effect shown / effect in data*
32. **Start bar charts at zero.** · W3 p6, p10, p12; W1 p111-112 · *bar chart guidelines*
33. **Line charts and dot plots may skip zero; say so and keep it honest.** · W3 p16-17; MV p86 (temperature exercise); VOTD Truncating · *dot plot guidelines*
34. **Use standard axes:** no inverted axes, no uneven time intervals. · W1 p53-54 (Florida gun deaths); W2 p68 · *use standard axes*
35. **Use dual axes with care.** Gridlines mislead. Prefer juxtaposed charts, a scatterplot, or an index chart, which has its own issues. · P2 p54-59; AV p70 · *dual axes charts*
36. **Avoid 3D** (perspective distorts). · W1 p47-48, p111-112 · *use 3D with caution*

### Ink, space, clutter
37. **Maximize the data-ink ratio** (= 1 − proportion of the graphic that can be erased). Remove noise and keep redundant coding only to enhance. · P2 p71-73; AV p58 · *data-ink ratio / signal-to-noise*
38. **"Be fair":** not every Tufte example is good. · P2 p74 · *Be fair*
39. **Balance information density and white space.** Find the sweet spot between dense and sparse. · W2 p22-23; W1 p44 · *information density; use space prudently*
40. **Avoid clutter:** too many lines, callouts or emphasized elements, and no white space. · W1 p45-46, p119 · *be careful with clutter*
41. **Use multi-functioning elements** (sparklines, scented widgets, color plus number) to raise data density. · AV p57-63 · *multi-functioning elements / data density*

### Chart choice (Week 3)
42. **Order bars by value to find values, or alphabetically to find labels.** Use horizontal labels (rotate the bars, not the labels) and neutral colors by default. Do not use hundreds of bars. Use a line chart if the categories are ordered in time. · W3 p5-6 · *bar chart guidelines*
43. **Avoid stacked bars and stacked areas for comparison.** Only the baseline layer is comparable. Use them only when the total makes sense and categories are few, or convert to small multiples. · W3 p11-12, p49 · *stacked bar guidelines*
44. **Avoid pies.** If you must use one: 3-5 categories, sum to 100 %, start at 12, sort large to small clockwise. "99.85% of the visualization community hates them." · W3 p39-45, p52; W1 p41-42 · *pie chart guidelines*
45. **Prefer bullet charts over gauges for KPIs.** They compare lengths instead of angles and are space efficient. · W3 p19-21 · *gauge vs bullet charts*
46. **Show the distribution, not just a summary.** Box plots hide data, so add strip/violin/beeswarm, or combine them as a raincloud. · W3 p26-37; VOTD Raincloud · *distributions*
47. **Normalize choropleths.** Larger regions look more important, and population density matters. Use a sequential segmented colormap, or graduated symbols to avoid confounding area with value. · W3 p103-110; VOTD Week7 Election maps · *choropleth issues*

### Views, interaction, color
48. **Use the Mantra:** "Overview first, zoom and filter, then details on demand." · W2 p37-40; P1 p8 · *Shneiderman's Mantra*
49. **Filter with dynamic queries and immediate feedback** (< 100 ms display update). Use scented widgets to show the filter's impact. · W2 p13; MV p99 · *dynamic queries / scented widgets*
50. **Link views:** a selection in one view is highlighted in all others in the same highlight color. · MV p64-69 · *linked highlighting / brushing / cross-filtering*
51. **Give small multiples comparable scales and encodings, logical arrangement, equal size, aligned axes.** · MV p45-47; W3 p114-117 · *small multiples*
52. **Design color defensively.** Avoid problematic pairs and compensate with another visual cue (shape, symbol, texture, direct label). Check with a simulator (Coblis). · CB p3, p11-14; PR p4 · *defensive design*

---

## 2. Channel effectiveness ranking (verbatim)

### 2a. Munzner ranking (P2 p35-37; image from Munzner, *Visualization Analysis and Design* 2014)
**Magnitude Channels: Ordered Attributes** (Best → Least, "Effectiveness"):
1. Position on common scale
2. Position on unaligned scale
3. Length (1D size)
4. Tilt/angle
5. Area (2D size)
6. Depth (3D position)
7. Color luminance ┐ "Same"
8. Color saturation ┘
9. Curvature ┐ "Same"
10. Volume (3D size) ┘

**Identity Channels: Categorical Attributes** (Best → Least): Spatial region → Color hue → Motion → Shape.

Principles on the same slide (verbatim):
- **expressiveness principle**: "match channel and data characteristics"
- **effectiveness principle**: "encode most important attributes with highest ranked channels"

### 2b. Mackinlay ranking table (P2 p39, "Ranking of visual variables, Mackinlay, 1987", decreasing)
| Quantitative | Ordinal | Nominal |
|---|---|---|
| Position | Position | Position |
| Length | Density | Color Hue |
| Angle | Color Sat. | Texture |
| Slope | Color Hue | Connection |
| Area | Texture | Containment |
| Volume | Connection | Density |
| Density | Containment | Color Sat. |
| Color Sat. | Length | Shape |
| Color Hue | Angle | Length |
| (Texture) | Slope | Angle |
| (Connection) | Area | Slope |
| (Containment) | Volume | Area |
| (Shape) | (Shape) | Volume |
(Grey entries mean "not applicable" in the original.)

### 2c. Empirical evidence (P2 p60)
Cleveland & McGill's results, replicated in "Crowdsourcing Graphical Perception" (Heer & Bostock, CHI 2010). Log error is lowest for **positions** (T1-T5) and higher for **angles** (T6, pie), **circular areas** (T7) and **rectangular areas**, aligned or in a treemap (T8-T9). Source: McGuffin slides.

### 2d. Related perception laws
- **Weber's law** (P2 p45-48): "just noticeable difference (JND) is proportional to the intensity of the original stimulus". The JND is the difference users detect in 50 % of trials.
- **Stevens' law** (P2 p50): "apparent magnitude of all sensory channels follows a power function based on the stimulus intensity". "As the dimension of an attribute increases, the degree at which we underestimate it increases."
- **Flannery's compensation** (P2 p61): perceptual scaling of proportional map symbols (makingmaps.net).
- **Preattentive properties** (P1 p57-58): Form (line orientation, line length, line width, size, curvature, shape, spatial grouping); Color (hue, intensity); Motion (flicker, direction of motion); Spatial position (2D position, stereoscopic depth, convexity/concavity). Threshold < 200-250 ms; eye movement takes ≥ 200 ms (P1 p48).
- **Texture** (P2 p12, Ware): dominant spatial frequencies must differ by a factor of 3-4, and orientations by > 30°.

---

## 3. Task taxonomy, data, design process (as taught)

### 3a. Design triangle (W1 p10, p19-20; P2 p32-38)
Data, Task and User around "Representation & interaction".
- **Expressiveness** (data-task): "Show exactly the information in the data. Nothing more and nothing less."
- **Effectiveness** (data-user): cognitive capabilities of the human visual system, the task, context.
- **Appropriateness** (task-user): cost-value ratio, mainly time (computation) and space (screen-space) efficiency.

### 3b. Purposes (W1 p79-89)
- **Explanatory**: present results. Communicate, explain, provide evidence, persuade; few variables but huge impact.
- **Analysis**: verify or falsify hypotheses. Show many variables, overview and detail, facilitate comparison.
- **Exploratory**: "Don't know what you're looking for", no a priori questions; vis used in "exploratory data analysis" (W1 p62, p85-86).
- **Form vs function** (W1 p88-89): static ↔ interactive form × explanatory ↔ exploratory function.

### 3c. Data types (W2 p7-9; P1 p5, p9)
- **Nominal**: unordered names; only (in)equality tests.
- **Ordinal**: ordered, not measurable; tests =, <, >.
- **Quantitative**: measured or simulated; full arithmetic.
- **Transformations**: nominal → ordinal by imposing an order; quantitative → ordinal by binning.
- **Structure** (Shneiderman 1996): 1-D, 2-D, 3-D, temporal, multi-dimensional, tree, network. Also tabular / relational / spatial (P1 p5).
- Exercises: iPhone model names are "ordered (intrinsic order)" (W2 p43); color codes are nominal (W2 p45). Missing values: erasing rows vs encoding as −10000 is a discussion exercise; never encode missing as a fake number (AV p69; W3 p128).

### 3d. Tasks (Shneiderman 1996; W2 p10-17, P1 p8)
1. **Overview**: gain an overview of the entire collection (zoomed-out view plus an adjoining detail view).
2. **Zoom**: zoom in on items of interest; smooth zoom preserves the sense of position and context.
3. **Filter**: filter out uninteresting items with dynamic queries; < 100 ms update.
4. **Details-on-demand**: select an item or group and get details (pop-up with attribute values).
5. **Relate**: view relationships among items.
6. **History**: undo, replay, progressive refinement.
7. **Extract**: extract sub-collections and query parameters (save, email, print).

**Generic operations** (W2 p28, data abstraction): sorting, filtering, characterizing trends and distributions, finding anomalies, correlation, outliers. Specific example: following a path in a graph.

**Per-chart tasks** (W3): bar = compare/lookup (p4); paired bar = compare within the same key (easier) or among keys (p9); pie = part-to-whole (p39, p42); scatter = find correlations (p71); heatmap = find clusters and outliers (p73); SPLOM = correlations between pairs (p78); line = trends (p90); small-multiple time series = trends and seasonal patterns (p116); hierarchy = hierarchical relationships and groups (AV p11); network = who is connected, central players, groups, cliques (AV p21).

**Visual-search tasks** (P1 p47): detection of a target among distractors; boundary detection; counting.

### 3e. Users' limits (W2 p18-23)
- Computational capacity: interactive response is needed.
- Perceptual and cognitive capacity: memory is limited; change blindness; vigilance degrades over hours.
- Display capacity: information density vs unused space, "ink-ratio" (Tufte).

### 3f. Nested design model (W2 p25-31, Munzner)
Domain problem characterization ⊃ data/operation abstraction design ⊃ encoding/interaction technique design ⊃ algorithm design. Each layer has its own validation. At the encoding layer: "Ensure no perceptual and cognitive principles are violated."
**Visualization pipeline** (W2 p32-35, Aigner 2011): raw data → data transformations → data tables → visual mappings → visual structures → views/view transformations; human interaction at any level.

---

## 4. Multiple views (MV deck, plus W3 and AV)

**Why** (MV p4-7): "**Eyes Beat Memory**: two simultaneous views have lower cognitive load than remembering previous view". Uses: comparison, details, exploration, focus + context, different data with the same encoding.
**Challenges**: real-estate trade-off (pop-up vs static side by side). The alternative is a single view changed through interaction. **Coordinated views** add linked interactions and boost expressivity.

### 4a. Layouts (MV p8-29): juxtaposition, superposition, explicit encoding
- **Juxtaposition** (p10-13): comparing two simultaneously visible views is easy; the alternative (change over time) uses working memory.
  - Design choices: which channels are shared, how much data is shared, whether navigation is synchronized.
  - *Uniform design* = same representation, different data. *Multiform* = different encoding, same data; it needs **linked highlighting**.
  - Cost: more display area (about 2×). It can encode more layers than superimposing.
- **Superposition** (p14-24): layers in the same space; no extra space and less eye movement.
  - Use non-overlapping ranges of visual channels (e.g., foreground/background).
  - "**Two layers is achievable, three with careful design**"; multiple layers only if each has few marks.
  - Line charts: "**up to a dozen lines**" (p21).
  - **Static layers** need selective attention. **Dynamic layers** are built on the fly by interaction (e.g., a highlighted layer).
- **Explicit difference encoding** (p25-29, p42-44): "only the difference" (a different encoding) or "original + difference".
  - Difference images (p27): similar regions in a cold color (blue), different regions in warmer colors (warmer = larger difference).
  - Over many steps: current step plus a de-emphasized previous step (p43-44).

### 4b. Data × encoding matrix (MV p31-33, Munzner 2014)
| | All data | Subset | None |
|---|---|---|---|
| **Same encoding** | Redundant | **Overview/Detail** | **Small Multiples** |
| **Different encoding** | **Multiform** | **Multiform, Overview/Detail** | No Linkage |

### 4c. Multiple-view systems (MV p34-47)
- **Overview & detail** (p35-37): one view shows a subset of the other; the overview gives context; the detail is usually larger; navigation is synchronized. Details-on-demand is typically another example, commonly multiform (e.g., a table).
- **Focus + context** (p39-41, p109-119): "Stresses the detail over the context".
  - Techniques: fish-eye lens, distortion, magnification, magic lens, bifocal distortion, hyperbolic trees (Lamping 1995).
- **Difference views** (p42): merge views to highlight the difference; "Color encoding the difference is a popular choice".
- **Small multiples** (p45-47; W3 p114-117).
  - A matrix of small visualizations, typically with the same encoding, aligned for comparison; a few dozen views with several hundred elements each. They are an "Alternative to animation (requires massive memory load)".
  - Guidelines: "Use appropriate charts for your data · Use comparable scales and comparable encodings · Arrange the individual charts logically · Use equal size for all charts & choose appropriate size". "Need to preserve axes, alignments: key to comparisons" (W3 p114).
  - Unshared axes are a pitfall (W3 p117). A fix for stacked areas is to convert them to small multiples (W3 p49).
- **Partitioning** (p48-62): choose split attributes and their order.
  - **Grouping** (e.g., grouped bars) compares across attributes in the same category. **Separating** compares individual attributes.
  - **Trellis** (Barley dataset): a 2D matrix of views; order by median to reveal outliers; "Proper ordering required".
  - **Recursive subdivision** (HiVE).

### 4d. Coordination / linking (MV p64-81)
- "Effective exploration comes from coordinating/linking views". Names: linked, coordinated, coupled views.
- **Linked highlighting**: "Items that are interactively selected in one view are immediately highlighted in all other views using the same highlight color". Also called **brushing** or **cross-filtering**; "Unleashes the full power of linked views"; typically a shared encoding in the color channel.
- **Linked navigation**: view parameters change through interaction with other views.
- **Linked filtering** (p69).
- **Links between views** (Sun et al. 2022, p70-76): aspects are *schema*, *structure* (one-to-one, one-to-many, many-to-many, bi-group), *weight* (strength) and *size* (count); relationships between items, between views, or hybrid. Design depends on these.
- Examples: TourVis (Díaz et al. 2021: selection → details, ranking at a point of interest); bike-sharing exercise where a sketched line selects similar stations, highlighted on a map (p88).

### 4e. Data reduction (MV p93-120)
- "Cannot show it all. Reduce!": derive new data, change the view over time, reduce items/attributes, facet across views.
- **Filter** (leave out) vs **aggregate** (merge); both are "extensively used in overviews".
- Spatial filtering = navigation: pan, zoom; *geometric* zoom vs *semantic* zoom (the representation adapts to screen space).
- Non-spatial filtering: **dynamic queries** with immediate feedback; **scented widgets** show the impact of filtering (p99; AV p59).
- Aggregation challenge: "**avoid averaging out signal**" (p101).
  - Histogram: "Choice of the bin size is crucial … may make the appearance completely different" (p102).
  - Boxplot (p104): see §6.
- **Levels of detail** (p113-116; Cockburn survey):
  - Overview+Detail = spatial separation.
  - Zooming (ZUIs) = temporal separation.
  - Focus+Context = no separation (single continuous view).
  - Visual cues = highlight, suppress or contextualize elements.
- **Baldonado's rules: not in the slides.** For a citation, use Munzner's matrix and Sun et al. 2022 instead. Baldonado, Woodruff & Kuchinsky (2000) give 8 rules for multiple views: diversity, complementarity, decomposition, parsimony, space/time resource optimization, self-evidence, consistency, attention management **(general, not in slides)**.

---

## 5. Color and colorblindness

### 5a. Color choice factors (P2 p11)
"Distinctness · Unique hues · Contrast with background · Number → Difference · Field Size · Color blindness, Conventions".
- Channel status (P2 p35): luminance and saturation are **magnitude** channels (ordered data); hue is an **identity** channel (categorical).
- Mackinlay (P2 p39): hue is 2nd for nominal but 9th for quantitative.

### 5b. Colormap rules found in the slides
- **Heatmap**: "Color by quantitative attribute (**ordered colormap**)" (W3 p73). Design decisions: size of cells (scalability), ordering of cells (search, patterns), color palette (W1 p134).
- **Choropleth**: "Encode: Color: **Sequential segmented colormap**"; data normalization and color mapping "are important design decisions" (W3 p103-105).
- **Unsuitable palettes**: W1 p26 shows a **rainbow** colormap on a Texas county map of a percentage, under "NOT VISUALIZATION: Using unsuitable palettes" (Wilke). This is the only rainbow reference; the slide does not use the word "rainbow".
- "Use color wisely" (W1 p51-52; a hatched bar chart with a green frame). "By default, prefer neutral colors" (W3 p6). One highlight hue over grey context (P1 p61-64).
- Encoding a 50-state categorical in hue is "Encoding too much or irrelevant information" (W1 p25).
- Difference encoding: cold = similar, warm = different (MV p27).
- **Diverging** colormaps are not named in any slide. Use one for signed data with a meaningful midpoint (e.g., a 0-centred anomaly) **(general, not in slides)**.
- Number of categories: pies 3-5 (W3 p42, p45); paired/stacked bars ≈ a dozen secondary keys (W3 p9, p11); about 12 superimposed lines (MV p21); 2-3 superimposed layers (MV p17).
- Rule of thumb ≤ 6-8 distinguishable categorical hues **(general, not in slides)**.
- Transparency: watch color continuity and ratio (P2 p26-27). PR p4: "When using colors with opacity different from zero, check the interactions with the other elements (are they visible?)".

### 5c. Colorblindness deck (CB, all 16 pages)
- **Prevalence** (p2): male red-green deficiency is ≈ 8 % in European Caucasians and ≈ 4-5 % in Asian populations; 6-7 % of men are color weak; 2-3 % of men are color blind.
- **Key aspects** (p3): understand the issues; "**Use defensive design**: Avoid issues · Compensate with other visual cues"; "You can always analyze your design" with the **Coblis color-blindness simulator** (color-blindness.com/coblis-color-blindness-simulator/).
- **Types** (p4):
  - Protanomaly (red-weak, ♂1 %), deuteranomaly (green-weak, ♂5 %), tritanomaly (blue-weak, 0.0001 %).
  - Protanopia (red-blind, ♂1 %), deuteranopia (green-blind, ♂1 %), tritanopia (blue-blind, < 0.03 %).
- **Confusions to avoid**:
  - "red- and green-blind people can't tell **red, green and brown** apart" (p5-6, traffic light).
  - "**red and green might look like grey**" (pink/turquoise/grey, p7).
  - "**red purple looks like blue**" (p8).
- **Safe bets** (p9): "IDEAL: combining **green with orange/red or blue if they have different lightnesses**".
- **Suggested palette** (p10, "my suggestion for a colorblind-safe palette"): four blues from dark to light, then red, orange and yellow (no hex given; vary lightness).
- **Other strategies** (p11-14):
  - Use a chart that does not require colors (a sorted single-hue bar chart instead of a pie).
  - Use a second visual cue such as symbols (✓/✗/−).
  - Use shapes in scatterplots.
  - Use **texture patterns, different line strokes, direct labelling**.
- **Resources** (p15): Datawrapper blog "colorblindness" parts 1-3.
- **Rubric** (PR p4): "Color blindness (e.g., coding anything just with a red-green palette may be problematic)" and "consistency of colors across the whole visualization (same color, same meaning in different charts)".
- **Prior project** (B_team_final/common.py, charts.py):
  - Okabe-Ito hues for causes (`#E69F00 #D55E00 #CC79A7 #0072B2 #8C8C8C`), checked with CVD ΔE ≥ 8.5.
  - Single-hue sequential ramp per measure (`oranges` ha, `purples` count, `yelloworangered` fire density); diverging `brownbluegreen` for climate.
  - Selection = black (`#1f1f1f`); context = grey `#8c8c8c` (3.4:1 vs white); faded `#d4d4d4` (focus + context).
  - Two periods by lightness, not hue (`#939393` vs `#3a3a3a`); station types by fill (black/white), not hue.
  - One color per meaning; titles carry the conclusion.

---

## 6. Uncertainty, distributions, statistical graphics (Tukey thread)

### 6a. Every Tukey-related mention
- **P1 p15**: the only explicit "**Tukey box plot**", in "Univariate data, From Mackinlay, 2000". Labels: "low", "Middle 50%", "high", and a central line labelled "**Mean**" (sic; a Tukey box plot marks the median **(general, not in slides)**).
- **MV p104** (boxplot as aggregation, not named Tukey): "Statistical summary of all the values … of a single quantitative attribute. Uses five derived variables … **median** (50% point), lower and upper **quartiles** (25% and 75% points), and the upper and lower **fences** (chosen values near the extremes, beyond which points should be counted as **outliers**)".
- **W3 p26-29**: box plots are "Useful for several distributions at the same time"; they show median, min, max and outliers.
  - Construction (p28): min, whisker, lower quartile Q1, median, upper quartile Q3, whisker, max, IQR.
  - "**Box plots hide/abstract too much data** … Hidden information may be relevant", so use violin plots, strip charts or beeswarm (p29).
- **EDA**: W1 p62 and p85-86 "Visualization very useful in **exploratory data analysis**". W1 p66: "Confirm expected and find unexpected patterns · Assess validity of statistical model". Anscombe 1973 (W1 p66-70); Datasaurus (W1 p73). Tukey coined "exploratory data analysis" (1977) and the box plot **(general, not in slides)**.
- **VOTD Raincloud** (Correll, EuroVis 2023): whiskers are ambiguous (full range vs **1.5·IQR**, following Frigge et al.). Datasets with very different shapes (unimodal, bimodal, skewed with an outlier) "all have the same five number summaries" and so an identical Boxplot (Choonpradub & McNeil).

### 6b. Distribution charts (W3 p23-37)
- **Histogram**: bin size matters; "Explore different bin sizes".
- **Strip chart**: shows all points, with jitter or blue-noise positioning.
- **Violin**: density plus box plot, mirrored "for aesthetical reasons"; may still hide data.
- **Ridge plot**: half-violin; allows more data, can overlap; "No accurate value estimation possible".
- **Raincloud** (W3 p37): "Combination of three plots to show both the distribution and the key statistics". Three variants: (a) Density-Jittered-Boxplot, (b) Boxplot-Strip-Mean Marker, (c) Histogram-Dot Plot-Mean+Interval.
- **Normalized stacked** and **overlaid density plots** (W3 p53-54).

### 6c. VOTD "Teru Teru Bōzu: Defensive Raincloud Plots" (Correll 2023)
- Cloud = shape (density/violin), rain = raw values, lightning = derived/inferential statistics.
- **Defensive** = components mutually cover each other's weaknesses. Recommendations:
  - Prefer a **strip plot** over a jittered dot plot ("textbook AVD failure").
  - Choose lightning to match the actual analysis; label what intervals mean.
  - Beware renormalization bias in histograms and heatmaps.
  - "The goal … should be not just to show the data, but to make sure the data have been communicated in a safe, robust, and truthful way."

### 6d. Uncertainty (AV p41-50; Padilla, Kay & Hullman)
- Data is commonly uncertain. Communicating it is hard: regular users are not used to it, and it "may lead to the readers considering your data is flawed", but it may be "highly necessary".
- **Most common methods** (p43):
  - Intervals and ratios: **error bars, box plot, icon array**.
  - Distributions: **violin plot, gradient plot**.
  - **Hypothetical outcome plot, quantile dot plot, ensemble plot**.
- "Also violin plots communicate uncertainty"; other: **line ranges** (p42).
- **Hybrid** (p44): **contour boxplot; probability density and interval plot**.
- **Hurricane cone** (p45-50): the cone contains the probable path and uncertainty grows with time. But cone size ≠ hurricane size, and impact falls outside the cone. Spaghetti plots mix non-models, old runs and statistical models (Dorian/Alabama fake map example).

### 6e. VOTD "What's really wrong with bar graphs of mean values" (Wilmer & Kerns)
- Mean bar graphs produce the **Bar-Tip Limit Error** (data drawn inside the bar), the **Dichotomization Fallacy** (no overlap) and the **Uniformity Fallacy** (no tails), with high inter-viewer variability.
- Alternatives: show individual points (dot plots, bee swarm, sinaplots with jitter/opacity/hollow markers), boxplots or violins, quantile dotplots, hypothetical outcome plots. References include "Error bars considered harmful" (Correll & Gleicher).

### 6f. Truncating axes (VOTD "Truncating the Y-Axis: Threat or Menace?", Correll, Bertini, Franconeri, CHI 2020)
- Bar charts with non-zero y "can visually exaggerate effect sizes". Truncation is "one of the cardinal sins", "quantified in Tufte's lie factor".
- Findings:
  - Exaggeration persists for **both bar and line charts**, and even with **broken-axis or gradient indicators**. "Merely indicating that truncation has occurred … may not be sufficient."
  - Line charts may legitimately use non-zero baselines: statistical process charts, index charts, climate anomaly charts (Ben Jones examples).
  - Skelton: a non-zero baseline is OK if zero is arbitrary (temperature) or a small important change is otherwise invisible. Tufte: "in a time-series, use a baseline that shows the data, not the zero point".
- Conclusion: designers "consider the scale of the meaningful effect sizes"; "no obvious way for designers to relinquish the responsibility of considering effect size".
- Course rule: bars from zero always (W3 p6). Line/dot plots may clip, but label the axes (MV p86).

---

## 7. Text and annotation

### VOTD "Why More Text is (Often) Better" (Stokes & Hearst, IEEE VIS 2022)
- Readers **preferred charts with more text**. They valued **context**, "even when it sacrificed simplicity".
- Guideline 1 (Stokes et al.): "**Rather than aiming for maximally minimalist design, annotate charts with relevant text.**" This counterbalances Tufte's data-ink minimalism.
- Readers **dislike redundant text** that restates what is visible (L1-L3: "Dislike that the maximum is annotated - that is visually obvious").
- They value **L4 external context** (causes, events). Semantic levels (Lundgard & Satyanarayan): L1 encoding, L2 statistical/relational, L3 perceptual/cognitive (trends), L4 external context.
- **Charts need titles**: they situate the reader. A missing title "violate[s] a schema".
- Ranking: CTA+ (title + many annotations) > CTA2 > CTA1 > CT > CO. Chart-only (CO) received the most requests for more text.
- Clutter is a minor issue compared with the benefit of context. "While [Rank] 1 is too busy, it is also the most informative."
- Annotations raise **suspicion of bias**: one-sided or slanted titles drive recall; over-interpreting "thinks for the reader". Readers notice context omitted as well as context shown.
- Guideline 4: "Consider a text-only variant that can stand alone." Text conveys narrative more naturally.
- Arrows that restate an obvious trend were seen as clutter.

### In the lecture decks
- Title with takeaway for explanatory vis (P2 p70); "Tell a story, give a message … write it" (W2 p5).
- Redundant numbers plus axes is double redundancy (W1 p113). An undescriptive title is criticized (W1 p114).
- Event annotation: "2005 Florida enacted Stand Your Ground" (W1 p53); WSJ measles heatmap "Vaccine introduced" line, normalized "per 100,000 people" (VOTD Week2 p7-8).
- Direct labelling as a CVD strategy (CB p14).
- PR p4: "add meaningful titles, labels, messages if necessary".
- Prior project: title = conclusion, subtitle = how to read it, annotations on key events.

---

## 8. What the professor grades (Project 1 statement, PR p2-4)

Project 1 is an "Explanatory visualization" with Altair and Streamlit; authors Pere-Pau Vázquez, Oscar Argudo, Imanol Muñoz; course 2026-2027.

**Per question/chart**:
- ≤ 200 words explaining design decisions: chart type and why, design-process steps, legibility / clutter reduction / distinguishing elements, "How would a person answer the question with your chart? What other alternatives did not work?"
- **Previous iterations are encouraged.**

**Final vis**: ≤ 200 words on consistency and aesthetics.

**Grade drivers ("Important remarks")**:
- the interview (individual grade: design decisions and implementation);
- the **number of variables** included, including calculated ones (aggregates, averages, maxima, minima);
- the **number of non-trivial tasks** properly solvable and documented. "**Adding extra tasks/questions is valued positively.**"

**Global checklist**:
- Thoroughly cleaned data (no N/A or undefined fields); a reproducible cleaning description.
- Code runs without errors.
- A step-by-step design process including "why you change something".
- Altair only (no mixing technologies).
- Author names in the notebook and the app ("About").

**Per chart**:
- Color blindness (no red-green-only coding).
- **Consistency of colors** (same color = same meaning).
- Meaningful titles, labels, messages.
- Check opacity interactions.
- "**Think whether you need to normalize values.**"

**Streamlit / final vis**:
- All questions on **one page**, max about 2 screens on a 15" laptop.
- Runs with `streamlit run`; includes a final vis answering all questions.
- "**Align things, be consistent**", using vertical and horizontal alignment to facilitate comparison.
- Extra questions go into the final vis.
- "Ensure charts can be visually compared properly (consider changing scales, palettes…)".
- "**Use space cleverly (put related things together and unrelated things far away)**", which is Gestalt proximity.
- "The higher the number of variables (and questions answered) included, the better."
- Pre-filter unused data.
- (Second lab) "**Ensure the default values make sense**" (meaningful initial state of selections).
- (Second lab) "**Minimize the number of interactions required to solve the problems.**"

**Exercises the professor uses**:
- Analyze a chart for 3D, non-zero bars, redundancy, perspective, lack of order, title, unjustified color, ink ratio (W1 p110-114).
- "What value would you think this visualization provides" (VOTD HomeworkValueofVisualization: OWID organic farming, Information is Beautiful water).
- Single-pen design (MV p84-86); dual-axis critique (AV p70); 50 creators × 10 years (AV p74).

---

## 9. Anti-patterns (things the course says not to do)

1. **Throwing data at any chart type** / random data → "visualization" (W1 p22-24, "NOT VISUALIZATION").
2. **Encoding too much or irrelevant information**, e.g., 50 state hues (W1 p25).
3. **Unsuitable palettes** (rainbow on an ordered percentage, W1 p26); careless color (W1 p51-52).
4. **3D charts and perspective projection** (W1 p47-48, p111-112); exploding 3D barrels with a huge lie factor (P2 p74).
5. **Bars not starting at zero**; bars whose heights are not proportional to their labels ("50 vs 47.4!!!", GPT-5 launch chart, W1 p127-131).
6. **Non-standard or inverted axes** (W1 p53-54).
7. **Unequal time intervals presented as equal**, and **cherry-picked timeline** points (W2 p65-68, Fox "Cost of gas", "Job loss by quarter": "Wrong scale!").
8. **Parts that already include the whole**, and **sizes not proportional** (Fox "Taxes at the pump", W2 p60-63).
9. **Lie factor ≫ 1** (fuel economy 14.8, P2 p62-64); unlabelled hidden baselines (baseline at −4200 $, P2 p68).
10. **Clutter**: spaghetti of dozens of colored lines (W1 p45-46); no white space, too many callouts or emphasized elements (W1 p119).
11. **Wasted space** (W1 p43-44, "Use space prudently!"); poor ink ratio encoding 4 values (W1 p114).
12. **Pies** for comparison, pies with > 5 slices, small multiples of pies (W1 p41-42; W3 p39-45).
13. **Stacked bars or areas** when comparison within or between groups matters, or when the total makes no sense (W3 p12, p49); streamgraphs for non-additive or negative data (W3 p99).
14. **Paired bars when one category is time** (W3 p10); bars for ordered time data where a line fits (W3 p6); hundreds of bars (W3 p6).
15. **Vertical labels** (W3 p5); unordered bars (W1 p113); unordered dot plots (W3 p16).
16. **Gauges** for KPIs (angle, space-hungry) when a bullet chart works (W3 p19-21).
17. **Dual axes** with misaligned gridlines (P2 p54-56); index charts lose context (P2 p58; W3 p94).
18. **Area or volume for precise magnitudes** (Stevens' law, P2 p50-53); circles and treemaps for exact comparison (P2 p60).
19. **Conjunction targets**; relying on preattentive search when users do not know what to look for (P1 p54-65).
20. **Moving, flickering or blinking elements** (P1 p65).
21. **Raw-count choropleths** (area bias, needs normalization; W3 p105-106; election maps VOTD); dot maps with overplotting (W3 p112).
22. **Venn diagrams for > 3-4 sets** → use UpSet (AV p37-39).
23. **Mean-only bar graphs** of human data (Bar-Tip Limit Error, Wilmer & Kerns); **boxplot-only** summaries that hide multimodality (W3 p29; raincloud VOTD); jittered rain (raincloud VOTD).
24. **Unlabelled intervals and error bars** (raincloud VOTD; "Error bars considered harmful").
25. **Averaging out the signal** when aggregating; a single arbitrary histogram bin size (MV p101-102).
26. **Encoding missing values as a sentinel number** (e.g., −10000) (AV p69); mixing gaps with zeros (prior project).
27. **Red-green-only coding**; red/green/brown, pink/turquoise/grey and purple/blue confusions (CB p5-8; PR p4).
28. **Inconsistent color meaning across charts** (PR p4).
29. **Exaggerated mark widths** (Tufte on 100-mile-wide cable lines, VOTD Week2 p3).
30. **Redundant annotations** that restate the visible (Stokes & Hearst); slanted or opinionated titles (suspicion of bias).
31. **Too many interactions**, or meaningless default states (PR p4, second lab).

---

### Short VOTD index (for citation)
- **Week1_VOTD**: The Pudding "film dialogue" by gender plus the Bechdel test.
- **Week2_VOTD**: Tufte's tweet on exaggerated line widths; WSJ infectious diseases heatmap (state × year, per 100,000, "Vaccine introduced" annotation).
- **Week3_VOTD**: NASA climate legacies and **warming stripes**.
- **Week5_VOTD**: Guardian gay-rights by state (variables: states, regions, laws; overview by color change).
- **Week7_VOTD**: US election maps (area vs population).
- **TruncatingtheYAxis**: Correll et al., CHI 2020.
- **HomeworkWhyMoreText…**: Stokes & Hearst, VIS 2022.
- **TeruTeruBozu…**: Correll, EuroVis 2023.
- **Homework2_2022_wilmer_kerns**: bar graphs of means.
- **HomeworkValueofVisualization**: "What value … does this visualization provide".
- **LetThereBeAnIphone**: NYT Magazine story of the 2007 iPhone demo. It contains no vis theory; the only parallel is rehearsing a "golden path" demo, relevant to the live interview **(interpretation, not in source)**.
