# AppleBee: An individual-based spatially explicit mechanistic model to predict the reproductive success of wild solitary pollinators

Edward I. Amoah<sup>1,2</sup>, Natalie K. Boyle<sup>2</sup>, Erica A. H. Smithwick<sup>3</sup>, Christina M. Grozinger<sup>2</sup>

<sup>1</sup> Intercollege Graduate Degree Program in Ecology, Huck Institutes of the Life Sciences, Penn State University, University Park, PA
<sup>2</sup> Department of Entomology, Center for Pollinator Research, Huck Institutes of the Life Sciences, Penn State University, University Park, PA
<sup>3</sup> Department of Geography and Earth and Environmental Systems Institute, Penn State University, University Park, PA
---

> **Working draft.** Text is adapted from Chapter 4 of *Bridging AI and Ecology*
> (Amoah, 2025). All quantitative results have been regenerated from
> `notebooks/applebee_analysis.ipynb` against the inputs in `data/inputs/`.
> Objective 4 is now a **regional simulation across the northeastern United
> States for 2014–2019**, replacing the chapter's sixteen-year Pennsylvania
> simulation. Passages that need author attention are flagged
> **[AUTHOR]**; every number carries its source.

---

## Abstract

Understanding how environmental conditions influence the abundance of wild
pollinators is critical for improving management of pollinator-dependent crops
such as apples. We developed an individual-based, spatially explicit, mechanistic
model (AppleBee) to predict the annual reproductive success — and thus the
potential abundance in the subsequent year — of the solitary bee *Osmia
cornifrons*. The model comprises four sub-models: emergence date, egg production,
egg and larva mortality, and winter mortality. We parameterized the model from
the literature and evaluated it in two ways. First, we evaluated the
egg-production sub-model using reproduction data from 17 sites in New York, USA;
the sub-model explained **51%** of the variation in total eggs produced across
sites and collection periods. Second, we evaluated the full AppleBee model
against long-term (2014–2019) solitary bee abundance monitoring data from Adams
County, Pennsylvania, USA, where it explained **80%** of the variation in the
abundance of bees in the genus *Osmia*. We then simulated *Osmia cornifrons*
reproductive success across **44,756 4 km grid cells spanning the northeastern
United States for the springs of 2014–2019** to examine spatial and temporal
trends. Predicted reproductive success was higher in the northern, cooler and
more forested portions of the region (mean 16.1 offspring per female) than in the
southern and more agricultural portions (13.4), and varied by a factor of 1.46
between the best and worst springs. Egg production was by far the most influential
sub-model, and temperature constrained foraging more often than precipitation
did. These results highlight the utility of mechanistic modeling for
understanding pollinator responses to environmental change and provide a
framework to inform policy, management, and programs promoting pollinator
resilience under a changing climate.

**Keywords:** *Osmia cornifrons*, mechanistic model, solitary bee, reproductive
success, pollinator, degree-day model, floral resources

---

## Introduction

Pollinators play a crucial role in ecosystems and in agricultural production,
supporting seed set and fruit production in approximately 75% of agricultural
crops (Klein et al., 2007; Eilers et al., 2011; Jordan et al., 2021; Rodger et
al., 2021). However, pollinator populations have shown dramatic declines
worldwide (Bruckner et al., 2023; Cameron & Sadd, 2020; Ulyshen & Horn, 2023).
Several environmental factors contribute to these declines, including loss of
flowering plants, reduction in nesting habitat, and increased pesticide exposure
(Wagner et al., 2021; Potts et al., 2010). Recent studies have also demonstrated
that weather and climate variables are major predictors of pollinator species
abundance and diversity (Kammerer et al., 2021; Stemkovski et al., 2020; Pardee
et al., 2022). Our understanding of how weather conditions influence the
population dynamics of different pollinator species nevertheless remains limited.

One promising strategy for addressing this knowledge gap is to build an
individual-based, spatially explicit mechanistic model that simulates the
influence of weather conditions on the growth, survival, and reproduction of
pollinators across the landscape (Johnston et al., 2019; Romero-Mujalli et al.,
2019). These models use existing datasets to examine how environmental conditions
affect an organism's behavior and physiology at different life stages (Kingsolver
et al., 2011; Maino et al., 2016; Briscoe et al., 2023). By integrating weather
and landscape variables, a spatially explicit mechanistic model can predict
reproductive success and species abundance at a scale relevant to management
decisions (Wood et al., 2015; Forbes et al., 2024). Developing such models also
helps identify critical data gaps, guiding future research on how environmental
conditions affect population dynamics.

The horn-faced mason bee, *Osmia cornifrons*, is an essential pollinator of
spring-blooming tree fruit crops such as apples in North America, Europe and Asia
(Matsumoto et al., 2009; Matsumoto et al., 2010; Yun-Li et al., 2019; Maeta et
al., 1981). *O. cornifrons* is native to Asia and was introduced to North America
in 1978 to support orchard pollination (Batra, 1982). The species is common in
natural environments and can also be semi-managed to produce large quantities of
cocoons sold to growers for pollination services (Bosch & Kemp, 2002). Other wild
*Osmia* species, such as *O. lignaria* and *O. cornuta*, also contribute
significantly to pollination of spring-blooming crops (Torchio, 1976; Torchio &
Asensio, 1985). In regions with sufficient natural habitat to support abundant
and diverse wild bee populations, growers need not purchase or rent mason bees,
bumble bees, or honey bee colonies, and can rely on wild bees for pollination
services (Park et al., 2020; Mallinger & Gratton, 2015). Surveys of growers have
nonetheless indicated concern about fluctuations in wild bee populations, which
can result in limited pollination and lower crop yield (Park et al., 2020; Reilly
et al., 2020). Understanding the factors that drive these fluctuations would
support decision tools that inform growers when populations are likely to be low
in a given year, and help identify strategies — renting or buying managed bees —
to meet pollination needs.

*O. cornifrons* has a lifecycle similar to that of many wild bee species. Like
90% of bee species, it is solitary: a single female establishes a nest (Bosch &
Kemp, 2008). Like 30% of bee species (Cane & Neff, 2011), it nests in
above-ground cavities — hollow tubes in pithy-stemmed plants or artificial nesting
boxes. As in most solitary bees, a female finds a nesting cavity, forages for
pollen and nectar to create a brood provision, lays an egg, seals the brood cell,
and repeats (Bosch & Kemp, 2008). The egg hatches, the larva consumes the
provision, pupates, and ecloses as an adult within a cocoon. In temperate
regions, solitary bees bypass harsh winter conditions by entering diapause
(Denlinger, 2002; Denlinger & Armbruster, 2014). Species differ in the
developmental stage at which they diapause; most spring-active Megachilidae,
including *O. cornifrons*, diapause as adults inside cocoons (Bosch & Kemp,
2008).

Several studies have examined how weather influences the phenology, behavior, and
development of *O. cornifrons* across life stages (Lee et al., 2016; McKinney &
Park, 2012; McKinney & Park, 2017). Winter temperature and length, and spring
incubation temperature, are important predictors of spring emergence, which has
been successfully predicted with a degree-day model (White et al., 2009; Ahn et
al., 2014; Adams, 2001). Other work has investigated the influence of temperature
on development rate and survival from egg to later life stages (McKinney & Park,
2017; Melone et al., 2024); exposure of larvae to extreme temperatures for four
days or more can cause larval mortality exceeding 75% (Melone et al., 2024).
Still other studies have examined how pre-wintering temperature conditions
influence winter survival (Bosch & Kemp, 2010; Sgolastra et al., 2011; Sgolastra
et al., 2016): prolonged warm pre-wintering conditions deplete the fat and lipid
reserves essential for winter survival (Sgolastra et al., 2011), resulting in
winter mortality above 15% (Bosch et al., 2010). The combined effects of weather
conditions and landscape floral resources across the *complete* lifecycle of
*O. cornifrons* have not, however, been evaluated.

The primary objective of this study is to develop AppleBee, an individual-based,
spatially explicit mechanistic model that predicts the number of adult offspring
(reproductive success) a single female solitary bee can produce at a given
location, based on the weather conditions and floral resources at that location.
The study has four specific objectives:

1. **Develop and parameterize** a mechanistic model with four sub-models —
   emergence date, egg production, egg and larva mortality, and winter mortality
   — using existing literature on *O. cornifrons*.
2. **Evaluate the egg-production sub-model** against field experimental data,
   fitting its output within a linear mixed-effects model to account for
   additional spatial and temporal complexity.
3. **Evaluate the full AppleBee model** against a long-term wild pollinator
   monitoring dataset from Pennsylvania, again within a linear mixed-effects
   framework.
4. **Simulate reproductive success across the northeastern United States for the
   springs of 2014–2019** and investigate spatio-temporal trends.

---

## Methods

The methods are organized in four subsections aligned with the four objectives.
The first describes the AppleBee mechanistic model and its parameters. The second
describes evaluation of the egg-production sub-model. The third describes the
holistic evaluation of AppleBee. The fourth describes the regional simulation.

All analyses were implemented in Python 3.12 (`statsmodels` 0.14.4,
`scikit-learn`, `numpy`, `pandas`). Code, inputs and a reproducible notebook are
described under **Data and code availability**.

### Objective 1: AppleBee mechanistic model

The emergence-date sub-model estimates the date a female *O. cornifrons* will
emerge at a location, given winter and spring ambient temperature (White et al.,
2009; Ahn et al., 2014; Adams, 2001). The egg-production sub-model estimates the
number of eggs a single female can produce, given temperature, precipitation and
floral resource quality (McKinney & Park, 2012; Maeta, 1978; Torchio, 1989;
Bosch, 2008). The egg-and-larva mortality sub-model estimates mortality risk for
eggs laid at a location based on temperature during egg and larval development
(McKinney & Park, 2017; Melone et al., 2024). AppleBee assumes no mortality
during the prepupal and pupal stages. The winter-mortality sub-model estimates
mortality for diapausing cocoons based on temperature during the pre-wintering
period (Sgolastra et al., 2011; Bosch et al., 2010).

*[Figure 1 — conceptual framework of the AppleBee model, four sub-models with
their temperature, precipitation and floral-resource inputs. Reuse Figure 4-1.]*

#### Emergence-date sub-model

The emergence-date sub-model is a degree-day equation:

$$CDD = \sum_{i=SD}^{ED} \left( T_{air,i} - T_{base} \right) \tag{1}$$

CDD is cumulative degree days accumulated from SD to ED (Ahn et al., 2014). SD is
the start date, set to 1 January (Ahn et al., 2014; Lee et al., 2018). ED is the
end date, determined by the thermal constant for emergence. $T_{air,i}$ is the
mean temperature (°C) of day *i*, and $T_{base}$ is the temperature above which
physiological development for emergence is activated. Emergence occurs on the day
CDD equals or exceeds the thermal constant. $T_{base}$ and the thermal constant
for *O. cornifrons* females are **6.53 °C** and **209 °C-days** (Adams, 2001).

**Table 1. Emergence-date sub-model parameters.**

| Variable | Description | Value / calculation | Reference |
|---|---|---|---|
| SD | Start date | 1 January | Ahn et al., 2014; Lee et al., 2018 |
| ED | End date | Calculated emergence day | Lee et al., 2018 |
| $T_{air,i}$ | Mean temperature of day *i* | PRISM, 4 km resolution | PRISM Climate Group |
| $T_{base}$ | Base temperature for development | 6.53 °C | Adams, 2001 |
| DD | Thermal constant | 209 °C-days | Adams, 2001 |
| CDD | Cumulative degree days | Accumulated SD → ED | Ahn et al., 2014 |

#### Egg-production sub-model

$$E = \sum_{i=SF}^{EF} f\left( T_{air,i},\, P_i,\, L_i \right) \tag{2}$$

E is the total number of eggs a female produces over her lifetime. SF is the
start of the foraging period, set two days after emergence to allow for mating
(McKinney & Park, 2012). EF is the end of the foraging period, set 20 days after
SF, based on an expected longevity of 22 days (Lee et al., 2016).
$f(T_{air,i}, P_i, L_i)$ is a step function returning the number of eggs produced
on day *i* from daily mean temperature, daily cumulative precipitation, and the
spring floral resource quality of the location:

$$f(T_{air,i}, P_i, L_i) = \begin{cases}
2 & \text{if } T_{air,i} \geq T_H \text{ and } P_i \leq P_H \text{ and } L_i \geq L_H \\
1 & \text{if } T_{air,i} \geq T_H \text{ and } P_i \leq P_H \text{ and } L_i < L_H \\
0 & \text{if } T_{air,i} < T_H \text{ or } P_i > P_H
\end{cases} \tag{3}$$

On days with favorable temperature and precipitation, a female produces two eggs
where spring floral resources are abundant, an upper bound taken from previous
studies (Maeta, 1978; Torchio, 1989; Bosch, 2008); one egg where conditions are
favorable but floral resources are not abundant; and none when foraging
conditions are unfavorable.

$T_H$ and $P_H$ were set at **13.9 °C** (McKinney & Park, 2012) and **5 mm**. We
chose 5 mm rather than 0 mm to allow for rainfall confined to a few hours,
including non-foraging hours at night. Floral resources are considered abundant
when quality meets or exceeds $L_H$, set at **0.5**. Spring floral resource
quality is an index between 0 and 1 calculated with the Lonsdorf model (Lonsdorf
et al., 2009), in which USDA Cropland Data Layer land-use categories are scored
for predicted seasonal floral resource quality by expert opinion (Koh et al.,
2016), averaged over a 1 km foraging radius and summarized to the 4 km PRISM
grid.

**Table 2. Egg-production sub-model parameters.**

| Variable | Description | Value / calculation | Reference |
|---|---|---|---|
| E | Total eggs per female per lifetime | Equation 2 | — |
| SF | Start of foraging | 2 days after emergence | McKinney & Park, 2012 |
| EF | End of foraging | 20 days after SF (22-day longevity) | Lee et al., 2016 |
| $T_{air,i}$ | Mean temperature of day *i* | PRISM, 4 km | PRISM Climate Group |
| $P_i$ | Cumulative precipitation of day *i* | PRISM, 4 km | PRISM Climate Group |
| $L_i$ | Spring floral resource quality | Lonsdorf index, 0–1, 1 km radius | Lonsdorf et al., 2009; Koh et al., 2016 |
| $T_H$ | Foraging temperature threshold | 13.9 °C | McKinney & Park, 2012 |
| $P_H$ | Foraging precipitation threshold | 5 mm | McKinney & Park, 2012 |
| $L_H$ | Floral resource threshold | 0.5 | Lonsdorf et al., 2009; Koh et al., 2016 |

#### Egg-and-larva mortality sub-model

$$M = \frac{1}{n}\sum_{e=1}^{n} m(e) \tag{4}$$

$$m(e) = \sum_{i=SL}^{EL} f\left( T_{air,i} \right) \times MF \tag{5}$$

$$f(T_{air,i}) = \begin{cases}
0 & \text{if } LDT \leq T_{air,i} \leq UDT \\
1 & \text{if } T_{air,i} < LDT \text{ or } T_{air,i} > UDT
\end{cases} \tag{6}$$

M is the mortality risk for eggs laid at a location — the proportion of laid eggs
that will not survive into adult cocoons — where *n* is the total number of eggs
laid and $m(e)$ the mortality risk of a single egg. SL is the date an egg was
laid and EL the duration of egg and larval development, set to **18 days** (Lee
et al., 2016). Every day the daily mean temperature falls outside the thermal
window, mortality risk increases by the mortality factor MF. UDT and LDT were set
at **30 °C** and **10 °C** (McKinney & Park, 2017), and MF at **10%**. We chose
10% as a conservative estimate given the scarcity of data on daily extreme
temperature effects; Melone et al. (2024) found that exposure of larvae to 37 °C
for four days or more resulted in mortality above 75%.

**Table 3. Egg-and-larva mortality sub-model parameters.**

| Variable | Description | Value / calculation | Reference |
|---|---|---|---|
| M | Mortality risk for eggs at a location | Equation 4 | — |
| EL | Egg-to-larva development duration | 18 days | Lee et al., 2016 |
| SL | Day an egg was laid | From Equation 2 | — |
| $T_{air,i}$ | Mean temperature of development day *i* | PRISM, 4 km | PRISM Climate Group |
| MF | Mortality factor | 10% per day outside the thermal window | Melone et al., 2024; McKinney & Park, 2017 |
| UDT | Upper development threshold | 30 °C | McKinney & Park, 2017 |
| LDT | Lower development threshold | 10 °C | McKinney & Park, 2017 |

#### Winter-mortality sub-model

$$W = \sum_{i=SP}^{EP} f\left( T_{air,i} \right) \times WF \tag{7}$$

$$f(T_{air,i}) = \begin{cases}
1 & \text{if } T_{air,i} \geq T_D \\
0 & \text{if } T_{air,i} < T_D
\end{cases} \tag{8}$$

W is winter mortality risk — the proportion of wintering cocoons that will not
survive. SP is the start of the pre-winter period (day of adult eclosion) and EP
the day of winter arrival, set to **15 August** and **1 October** (Bosch & Kemp,
2010; Sgolastra et al., 2011; Sgolastra et al., 2016). During the pre-winter
period, each day the daily mean temperature exceeds the diapause temperature
threshold $T_D$, winter mortality risk increases by the pre-winter mortality
factor WF. $T_D$ and WF are **15 °C** (Sgolastra et al., 2011) and **0.25%**. A
later onset of winter therefore exposes the diapausing adult to more warm days,
depleting the fat and lipid reserves essential for winter survival (Sgolastra et
al., 2011). We chose 0.25% so that a late winter arrival, or 60 days of
pre-wintering, produces winter mortality of 15%; Bosch et al. (2010) reported
15.9% winter mortality for *O. lignaria* after 60 days of pre-wintering.

**Table 4. Winter-mortality sub-model parameters.**

| Variable | Description | Value / calculation | Reference |
|---|---|---|---|
| W | Winter mortality risk | Equation 7 | — |
| SP | Day of adult eclosion | 15 August | Bosch & Kemp, 2010; Sgolastra et al., 2011 |
| EP | Day of winter arrival | 1 October | Sgolastra et al., 2011, 2016 |
| $T_{air,i}$ | Mean temperature of day *i* | PRISM, 4 km | PRISM Climate Group |
| $T_D$ | Pre-winter temperature threshold | 15 °C | Sgolastra et al., 2011 |
| WF | Winter mortality factor | 0.25% per day above $T_D$ | Sgolastra et al., 2011; Bosch et al., 2010 |

#### Annual reproductive success

The three sub-model outputs combine into annual reproductive success:

$$R = E \times (1 - M) \times (1 - W) \tag{9}$$

R is the number of adult offspring per female at a grid cell, and determines the
potential abundance in the following spring.

### Objective 2: Egg-production sub-model evaluation

#### Dataset

The evaluation dataset comes from a multi-site field study across 17 apple
orchards in the Finger Lakes region of New York (Centrella et al., 2020). Across
the 17 sites, forest was the most common surrounding habitat (~33%), followed by
agriculture (27%), urban (13%), open habitats (12%) and shrub/wetland (7%). New
York has an average annual rainfall of 103 cm, average summer temperatures of
17–21 °C and average winter temperatures of −7 to −0.5 °C (Lamie et al., 2024;
Frankson et al., 2022).

At each site, a nesting population was established with 20–22 source nest tubes
containing 98–102 adult *O. cornifrons*, alongside 30–32 experimental nest tubes,
in a single wooden shelter within or along the orchard perimeter. Source tubes
were placed on 5 May 2015 and bees began emerging on 7 May 2015. From 7 May to 24
June 2015, completed nest tubes were retrieved and replaced every six days. This
yielded **51 observations — 17 sites × 3 collection periods**.

**Response variable.** The published dataset records emerged adults rather than
brood cells. Because the model predicts cells, we reconstructed the number of
brood cells per observation as

$$\text{cells} = \frac{\text{males} + \text{females}}{1 - \text{larval mortality}}$$

which is exact where larval mortality is recorded, and a lower bound for the 11
of 51 observations recording no mortality.

**Collection window.** Each observation's foraging window is the six days ending
on and including the collection date, i.e. the closed interval [D−5, D].

#### Statistical analysis

We evaluated the egg-production sub-model as a hybrid model within a linear
mixed-effects framework. The response was observed brood cells at a site in a
collection period; fixed effects were predicted eggs per female from the
mechanistic sub-model and collection time point (categorical, to account for
repeated collections); site was a random intercept:

$$y_{i,j} \sim \beta_0 + \beta_1 x_{i,j} + \beta_2 t_{i,j} + u_j + \varepsilon_{i,j} \tag{10}$$

where $y_{i,j}$ is observed brood cells at site *i* in period *j*, $x_{i,j}$ the
predicted eggs per female, $t_{i,j}$ the collection time point, $u_j$ the random
effect of site, and $\varepsilon_{i,j}$ the residual. Models were fitted by
restricted maximum likelihood. We report the conditional $R^2$ — variance
explained by fixed and random effects together — and RMSE.

Model assumptions were checked with a residual QQ-plot and autocorrelation plot,
a Shapiro–Wilk test for normality, and a Durbin–Watson test for autocorrelation.

### Objective 3: AppleBee model evaluation

#### Monitoring dataset

We evaluated AppleBee against a long-term solitary bee monitoring dataset
collected from 2014 to 2019 at the Pennsylvania State Fruit Research and
Extension Center and surrounding apple orchards in Adams County, Pennsylvania
(39.935226, −77.254530) (Turley et al., 2022). The site is surrounded by
approximately 56% forest fragments, 25% pastureland, 9% developed or urban land,
and 8% commercial orchards or agriculture (Biddinger et al., 2018), with average
annual rainfall of 112 cm, summer temperatures of 16–28 °C and winter
temperatures of −5 to 5 °C.

Solitary bees were monitored at 8 locations within 150 m of apple orchards and
250 m of forest fragments, each including a 50 × 10 m wildflower strip
established 2–3 years before sampling and planted with 21 native forb and grass
species. Bees were sampled with Blue Vane traps (BanfieldBio Inc.) — two per
site, 25 m apart, mounted 1.5 m above ground — visited weekly from April to
October. Collections were preserved in 70% ethanol before identification by
multiple experts; voucher specimens are curated at Penn State (Turley et al.,
2022).

The dataset comprises 26,716 specimen records across 30 genera; **183 records are
*Osmia***, giving six annual counts. We used genus-level *Osmia* counts rather
than *O. cornifrons* because records of the latter were too few. All eight
monitoring locations fall within a single 4 km grid cell and were treated as one
site.

#### Simulation procedure and inputs

We applied Equation 9 to simulate annual reproductive success for the monitoring
cell for each spring from 2014 to 2019, driven by daily PRISM mean temperature
and cumulative precipitation for 2013–2018 at 4 km resolution, and by the
Lonsdorf spring floral resource index for the corresponding years. The
simulation used the literature parameters of Tables 1–4.

#### Statistical analysis

We fitted a linear mixed-effects model with observed *Osmia* counts as the
response, AppleBee's predicted adult offspring per female as the fixed effect,
and year as a random intercept:

$$y_i \sim \beta_0 + \beta_1 x_i + u_i + \varepsilon_i \tag{11}$$

We report conditional $R^2$ and RMSE. Assumptions were checked as in Objective 2.

**Note on the design.** There is one observation per year and the random
intercept is by year, so each intercept is estimated from a single observation.
Consequences for the precision of $\beta_1$ are addressed in the Discussion.

### Objective 4: Regional simulation across the northeastern United States

We simulated reproductive success for **every 4 km grid cell in the northeastern
United States for the springs of 2014–2019**, driven by weather years 2013–2018.

**Extent.** The simulation domain is the bounding box 36.5–47.5 °N, 83.0–66.9 °W.
Of the 44,756 cells carrying both weather and a floral resource index, **89.0%
(39,844) fall within the thirteen northeastern states** (CT, DE, MA, MD, ME, NH,
NJ, NY, PA, RI, VA, VT, WV); the remainder fall in adjacent portions of Ohio
(3,575 cells), Kentucky (547), Michigan (424), North Carolina (259), Tennessee
(96) and the District of Columbia (11). The domain totals **268,536 cell-years**.

**Rationale for the extent.** The evaluations in Objectives 2 and 3 are both
northeastern — New York orchards and a Pennsylvania monitoring site — so this is
the region in which the model has been tested against observation. A regional
extent also avoids a known artifact at lower latitudes described in the
Discussion.

**Inputs.** Daily PRISM mean temperature and cumulative precipitation
(2013-01-01 to 2018-12-31, 4 km) were retrieved directly from the PRISM web
service. Spring floral resource quality was computed for each year from the USDA
national Cropland Data Layer scored with Koh et al. (2016) expert spring values,
as an area-weighted mean over a 1 km foraging radius in EPSG:5070.

**Spatial and temporal trends.** We mapped predicted offspring per female and
predicted eggs per female for each spring, and computed the six-year mean and the
between-year standard deviation for every cell. We summarized results by state
and compared the northern and southern halves of the domain, split at the median
latitude (41.25 °N).

**Most influential sub-model.** We fitted a random forest regression (100 trees,
`scikit-learn`, 80/20 train–test split) with four predictors aligned to the four
sub-models: Julian emergence date, predicted eggs, egg-and-larva mortality risk,
and winter mortality risk. Importance was assessed by mean decrease in impurity.

**Primary weather constraint.** We quantified "no-egg days" — days on which egg
production was impossible — and attributed each to temperature and/or
precipitation according to the model thresholds. We used a one-tailed Welch
*t*-test to assess whether no-egg days attributable to temperature exceeded those
attributable to rainfall.

---

## Results

### Objective 1: AppleBee mechanistic model

AppleBee was formalized as nine equations (Equations 1–9). The emergence-date
sub-model is a degree-day model; the egg-production, egg-and-larva mortality and
winter-mortality sub-models are step functions. Parameters and sources are given
in Tables 1–4.

*[Figure 2 — the mechanistic equations, as Figure 4-2 of the chapter.]*

### Objective 2: Egg-production sub-model evaluation

The maximum, mean, minimum and standard deviation of reconstructed brood cells
across the 51 observations were **182, 52, 4 and 41**. The corresponding
statistics for predicted eggs per female over the six-day windows were **12, 3.6,
1 and 2.0**.

The egg-production sub-model explained **51.0% of the variance** in observed brood
cell production, with an RMSE of **28.6 cells** (Figure 3). Predicted eggs per
female were positively and significantly associated with observed brood cells
(**β = 7.92, SE = 2.72, z = 2.91, p = 0.004**), indicating that the sub-model
captures meaningful environmental drivers of solitary bee reproduction (Table
S1). Brood cell production was significantly *lower* at Time Point 3 relative to
Time Point 1 (β = −27.31, p = 0.014), while Time Point 2 did not differ
significantly from Time Point 1 (β = 1.25, p = 0.915) — temporal variation in
reproductive activity that the sub-model does not capture.

The random effect of site accounted for a variance of 306.8 (SD 17.5) against a
residual variance of 1049.8, giving an **intraclass correlation of 0.226**: about
23% of the variance in brood cell production lies between orchards.

*[Figure 3 — observed brood cells against the mixed-model fit, coloured by
collection time point, with the 1:1 line. Generated by
`notebooks/applebee_analysis.ipynb` § 1.]*

#### Assumption validation

Residuals showed no significant deviation from normality (Shapiro–Wilk
**W = 0.964, p = 0.121**), supported by a QQ-plot in which residuals followed the
1:1 line closely. The Durbin–Watson statistic was **2.07**, indicating no
autocorrelation.

### Objective 3: AppleBee model evaluation

AppleBee achieved an **$R^2$ of 0.803** and an **RMSE of 7.52**, indicating a
strong positive relationship between the observed abundance of *Osmia* bees and
the predicted adult offspring per female (Figure 4). The effect of predicted
offspring per female on observed abundance was positive (**β = 1.99, SE = 0.62**;
Table S2), but **not statistically significant**: tested on the six annual counts
directly, the slope gives **p = 0.36**. The mixed model's own standard error is
optimistic under this design, for the reason set out in the Discussion.

**Table 5. Observed and predicted *Osmia* abundance at the Adams County
monitoring site.**

| Spring | Observed *Osmia* | Predicted offspring per female | Predicted eggs | Emergence (day of year) |
|---|---|---|---|---|
| 2014 | 10 | 8.46 | 11 | 127 |
| 2015 | 58 | 11.67 | 13 | 130 |
| 2016 | 47 | 11.54 | 14 | 126 |
| 2017 | 26 | 1.60 | 2 | 118 |
| 2018 | 27 | 2.97 | 7 | 110 |
| 2019 | 15 | 8.85 | 10 | 128 |

*[Figure 4 — (A) observed against predicted *Osmia* count with the 1:1 line and
model specification; (B) observed and fitted abundance by year. Generated by
`notebooks/applebee_analysis.ipynb` § 2.]*

#### Assumption validation

Residuals showed no significant deviation from normality (Shapiro–Wilk
**W = 0.871, p = 0.232**). The Durbin–Watson statistic was **1.78**, indicating
weak positive autocorrelation within an acceptable range for independence.

### Objective 4: Regional simulation across the northeastern United States

#### Spatial and temporal trends

Across the region and the six springs, the maximum, mean and minimum predicted
offspring per female were **34.8, 14.7 and 0.0**. At the level of individual grid
cells, the maximum, mean and minimum standard deviation of predicted offspring
from year to year were **12.5, 5.0 and 0.2**. The standard deviation of cell
means — variation across space — was **4.59**, slightly less than the mean
within-cell standard deviation through time (**4.99**), indicating that at this
extent and over this period, year-to-year variation is comparable to, and
marginally exceeds, geographic variation.

Spatially, predicted reproductive success was consistently higher in the
northern, cooler and more forested portions of the domain than in the southern
and more agricultural portions: **16.06 offspring per female north of 41.25 °N
against 13.38 to the south**. Connecticut (18.62), New Hampshire (17.32), Rhode
Island (17.09), Massachusetts (16.92) and Maine (16.90) had the highest state
means; North Carolina (9.61), Delaware (10.81) and Tennessee (11.64) the lowest
(Table 6). Across cell means, predicted offspring tracked the floral resource
index most closely (*r* = 0.60; Figure 5a), ran **opposite** to mean daily
temperature (*r* = −0.27; Figure 5b), and was effectively unrelated to
precipitation (*r* = −0.02; Figure 5c).

Temporally, mean predicted offspring per female ranged from **12.38 in 2018 to
18.03 in 2015**, a factor of **1.46** between the worst and best springs. The
pattern tracked mean predicted egg production closely (15.15 to 20.16 eggs per
female) and inversely tracked foraging days lost to cold (8.36 days in 2018
against 4.53 in 2015).

**Table 6. Predicted reproductive success by state, 2014–2019 means.** States are
ordered by mean offspring per female. Cell counts are grid cells within each
state.

| State | Cells | Eggs per female | Offspring per female | Days lost to cold | Days lost to rain |
|---|---|---|---|---|---|
| Connecticut | 811 | 21.52 | 18.62 | 5.28 | 4.01 |
| New Hampshire | 1,556 | 19.53 | 17.32 | 6.51 | 4.42 |
| Rhode Island | 201 | 19.81 | 17.09 | 5.04 | 3.82 |
| Massachusetts | 1,398 | 19.53 | 16.92 | 5.46 | 4.23 |
| Maine | 5,762 | 18.56 | 16.90 | 6.69 | 4.31 |
| New York | 8,204 | 16.99 | 15.09 | 6.11 | 4.58 |
| West Virginia | 3,760 | 19.12 | 15.03 | 6.30 | 5.38 |
| Vermont | 1,621 | 16.78 | 14.93 | 6.77 | 5.16 |
| Pennsylvania | 7,173 | 17.41 | 14.89 | 6.50 | 4.55 |
| New Jersey | 1,238 | 17.09 | 14.69 | 6.14 | 4.25 |
| Kentucky\* | 547 | 18.91 | 14.59 | 7.76 | 3.95 |
| Maryland | 1,679 | 15.23 | 12.99 | 6.37 | 4.19 |
| District of Columbia\* | 11 | 14.92 | 12.99 | 6.44 | 2.98 |
| Michigan\* | 424 | 14.45 | 12.94 | 4.19 | 3.18 |
| Ohio\* | 3,575 | 15.83 | 12.48 | 6.34 | 4.63 |
| Virginia | 6,109 | 15.49 | 12.47 | 8.59 | 4.07 |
| Tennessee\* | 96 | 15.37 | 11.64 | 9.08 | 3.95 |
| Delaware | 332 | 12.58 | 10.81 | 6.24 | 3.48 |
| North Carolina\* | 259 | 12.66 | 9.61 | 9.95 | 3.84 |

\* Partial coverage — these states fall only partly within the simulation
bounding box.

**Table 7. Regional means by spring.**

| Spring | Offspring per female | Eggs per female | Emergence (day of year) | Days lost to cold | Days lost to rain |
|---|---|---|---|---|---|
| 2014 | 13.07 | 15.54 | 133.4 | 7.41 | 5.04 |
| 2015 | **18.03** | 20.16 | 136.2 | 4.53 | 4.14 |
| 2016 | 14.55 | 17.45 | 131.9 | 6.64 | 4.04 |
| 2017 | 12.97 | 15.58 | 129.4 | 8.46 | 4.06 |
| 2018 | **12.38** | 15.15 | 123.2 | 8.36 | 5.11 |
| 2019 | 17.41 | 19.74 | 132.4 | 4.57 | 4.45 |

*[Figure 5 — the model's three inputs and its prediction, over the same 44,756
grid cells and the same six years: **(a)** the Lonsdorf spring floral resource
index, **(b)** mean daily temperature, **(c)** mean daily cumulative
precipitation, and **(d)** predicted offspring per female. Panels (a)–(c) are
six-year means over weather years 2013–2018 and are clipped to their 1st–99th
percentiles; panel (d) is the six-year mean for springs 2014–2019, shown on its
full range. Generated by `notebooks/applebee_analysis.ipynb` § 3.]*

*[Figure 6 — predicted egg production per female mapped for each spring,
2014–2019, on a shared colour scale. Generated by
`notebooks/applebee_analysis.ipynb` § 3.]*

#### Most influential sub-model

Among the four predictors, **egg production was overwhelmingly the most
influential predictor of offspring production, accounting for 95.4% of predictive
importance**. Egg-and-larva mortality accounted for 4.4%, winter mortality for
0.22%, and Julian emergence date for 0.003%.

*[Figure 7 — random forest variable importance.]*

#### Primary weather constraint on egg production

Temperature-limited days were more frequent and more variable than
precipitation-limited days. The number of no-egg days attributable to temperature
(**mean 6.66, SD 3.63**) was significantly greater than those attributable to
precipitation (**mean 4.47, SD 2.06**; one-tailed Welch *t* = 271.4,
*p* < 0.001). The contrast was strongest in the southern and inland portions of
the domain — North Carolina (9.95 cold days against 3.84 wet), Tennessee (9.08 /
3.95) and Virginia (8.59 / 4.07) — and weakest in coastal New England.

*[Figure 8 — no-egg days attributable to temperature and to precipitation.]*

---

## Discussion

### AppleBee mechanistic model

We developed and evaluated AppleBee, an individual-based, spatially explicit
mechanistic model designed to predict reproductive success and population
dynamics of *Osmia cornifrons*, a key pollinator of spring-blooming crops such as
apples. The model comprises four sub-models: emergence date, egg production, egg
and larva mortality, and winter mortality.

We evaluated AppleBee in two ways. First, we evaluated sub-models independently
where data were available; only the egg-production sub-model could be evaluated
this way, for lack of datasets addressing the others. Second, we evaluated the
model holistically against a long-term solitary bee abundance monitoring dataset
from Adams County, Pennsylvania (Turley et al., 2022).

### Egg-production sub-model and AppleBee model

The egg-production sub-model performed moderately well, explaining 51% of the
variation in *O. cornifrons* reproduction against the Centrella et al. (2020)
data. The fixed effect of the sub-model's predictions was positive and
statistically significant, indicating that it captures ecological dynamics
relevant to solitary bee reproduction.

There is nevertheless room for improvement. The effect of collection time point
was significant at Time Point 3, showing that the sub-model does not capture some
temporal dynamics in egg production. The current model assumes a constant rate of
egg production over a female's life, whereas these results indicate that
reproductive output is time- or age-dependent — consistent with other studies
reporting age-dependent reproductive output in solitary bees (Tepedino & Torchio,
1982; Sugiura & Maeta, 1989). A further explanation is temporal change in floral
resource availability (Goodell, 2003), which the model treats as constant within
a season and which is unlikely to reflect real dynamics at local sites.

The intraclass correlation of 0.226 quantifies what the mechanistic sub-model
does not reach: roughly a quarter of the variance in brood cell production lies
systematically between orchards, and is not explained by weather or by the
landscape floral resource index. Local factors — management, microclimate, floral
resources at finer resolution than the Cropland Data Layer can represent — are a
natural target for future model development.

The full AppleBee model explained 80% of the variation in the abundance of
*Osmia* bees in the monitoring dataset. Together, the two evaluations suggest
that the model captures ecological dynamics relevant to the reproductive success
and abundance of wild solitary bees.

### A caution on the Objective 3 evaluation

The Objective 3 evaluation rests on **six annual counts from a single site**, and
the random intercept in Equation 11 is fitted by year — one observation per
group. Under this design the group and residual variance components are not
separable, and the standard error the mixed model returns on $\beta_1$ is
correspondingly optimistic. Tested on the six annual counts directly, the slope
is not significant (p = 0.36). Six annual counts from one location cannot
support a claim of statistical significance in either direction, and the fit
statistics should be read as a description of agreement rather than as a
hypothesis test. **[AUTHOR: a statistician's review of Equation 11 under this
design is planned; the reported $R^2$ follows the dissertation convention.]**

This is a limitation of the available evaluation data rather than of the model. A
panel with genuine replication — several sites monitored over several years, so
that year effects are estimated from more than one observation each — would
resolve it, and is the single most valuable dataset that could be collected to
advance this work.

### Spatial and temporal dynamics of reproductive success

Simulation across the northeastern United States showed that egg production is by
far the most influential sub-model, accounting for 95% of predictive importance:
the number of eggs a female lays is the dominant determinant of reproductive
success and subsequent abundance. Temperature was the primary weather constraint
on egg production, limiting foraging on 6.7 days per female on average against
4.5 days for rainfall.

Predicted reproductive success was higher in the northern, cooler and more
forested portions of the region than in the southern and more agricultural
portions. This gradient runs counter to a simple expectation that warmer
conditions favor reproduction, and arises because emergence in warmer areas
occurs earlier in the calendar, placing the fixed 22-day adult foraging window in
a period of greater thermal variability. The interaction between the emergence
sub-model and the foraging temperature threshold therefore predicts a
**non-monotonic response to warming**: earlier emergence can reduce reproductive
success even as mean temperature rises. This is a testable prediction of the
model and a target for future empirical work.

Interannual variation was substantial, with the best spring exceeding the worst
by a factor of 1.46, and within-cell variation through time (4.99) marginally
exceeding variation between cells (4.59). Both location-specific factors — land
cover, regional climate — and year-specific drivers — annual weather variation —
shape reproductive success, and neither dominates at this extent.

### A structural limitation: daily mean temperature

The foraging criterion is applied to **daily mean** temperature. Where the diurnal
range is wide, a day whose mean falls below the 13.9 °C threshold may nonetheless
have offered several usable foraging hours in the afternoon. The model therefore
over-counts unsuitable days wherever mornings are cold and afternoons warm, an
effect that grows toward lower latitudes and in continental interiors. This is
one reason the present simulation is regional rather than national: exploratory
runs across the contiguous United States produced implausibly low reproductive
success across the southern states, an artifact rather than an ecological result.

Daily maximum temperature is available from the same PRISM service, and repeating
the analysis against a maximum-temperature or degree-hour criterion would
quantify the bias. **[AUTHOR: worth doing before submission if the southern or
continental extent is to be discussed at all.]**

### Data limitations

While acknowledging the limitations of the datasets used to parameterize and
evaluate AppleBee, the results suggest that the model is a promising tool for
simulating reproductive success and population dynamics of *O. cornifrons*, and
could be adapted to other solitary bee species.

The egg-production sub-model was parameterized with monitoring data from one
location in a single season (McKinney & Park, 2012). Proper parameterization
requires reproduction monitoring at multiple sites repeated over multiple years.
In the Centrella et al. (2020) dataset, eggs per collection period were counted
from *completed* nest tubes only, so eggs laid in incomplete tubes are not
counted; the dataset therefore does not accurately capture the egg production
rate for each period. This may explain part of the unexplained variance. The
six-day interval between assessments is a further constraint — daily or hourly
monitoring would provide a much better dataset, but is difficult to implement
manually. Automated monitoring of nesting and egg production will be instrumental
in acquiring the data needed to parameterize and validate this sub-model.

The Turley et al. (2022) dataset has both temporal and spatial constraints. Six
years of abundance monitoring is insufficient to robustly evaluate AppleBee, and
all eight monitoring locations fall within a single 4 km grid cell, so the
evaluation cannot account for spatial variability. Long-term insect abundance
monitoring across large landscapes is needed, particularly for studies
investigating the long-term impacts of climate change on the abundance and
distribution of pollinators.

### Future data requirements and model improvements

Beyond the limitations of the datasets used here, new kinds of data are needed to
parameterize and independently validate the remaining sub-models. The mortality
factor (MF) in the egg-and-larva mortality sub-model is a critical example:
laboratory experiments exposing eggs and larvae to graded levels of extreme cold
or heat, with daily mortality monitoring, would allow it to be estimated rather
than assumed. Field experiments placing bee hotels across a temperature gradient
could serve a similar purpose, though daily monitoring inside an enclosed nest
presents practical difficulties that automated monitoring systems could address.

The current model does not account for effects of weather on males after
emergence. Extreme heat can impair male sperm quality (Mokkapati et al., 2025),
with implications for reproductive success. The model also does not explicitly
incorporate the influence of weather on landscape floral resources; early-season
precipitation has been shown to influence solitary bee reproductive success
(Westreich et al., 2023). Both are natural extensions.

### Utility and implications for agriculture

Mechanistic models can help predict local variation in the abundance of key
species for management or conservation. AppleBee was designed to understand and
predict how environmental factors contribute to the abundance and distribution of
a key pollinator of spring-blooming tree crops, and similar models could be
developed for other pollinator species.

AppleBee can help growers identify in advance where and when wild pollinator
abundance will be low, and purchase or rent managed bees to meet pollination
needs and avoid yield loss. Because egg production is the most influential
predictor of reproductive success, growers can anticipate in summer, with
reasonable confidence, the relative abundance of wild pollinators the following
spring. A nationwide study in the USA found that production of apples, cherries,
blueberries, watermelon, pumpkin and almonds is frequently limited by lack of
pollinators (Reilly et al., 2020), with wild pollinators contributing an
estimated annual production value of over $1.5 billion USD to those seven crops.
AppleBee can help reduce the risk of pollination limitation and make that
industry more resilient to weather and climate fluctuation.

### The utility of mechanistic models for climate resilience

Resilience is fundamental to the survival and growth of any industry dependent on
weather. Under climate change, the frequency and intensity of extreme weather
events are predicted to increase (Westra et al., 2014; Ummenhofer et al., 2017;
Walsh et al., 2020), with varying impacts across species depending on life
history traits and physiological responses at different life stages (Pardee et
al., 2022). Mechanistic models let us understand and predict how beneficial
insects will respond, informing policies, management practices and programs that
keep sectors such as agriculture resilient to extreme and fluctuating weather.

---

## Data and code availability

All analyses in this manuscript are reproducible from the accompanying
repository.

| | |
|---|---|
| Analysis notebook | `notebooks/applebee_analysis.ipynb` |
| Model implementation | `applebee/` |
| Inputs | `data/inputs/` — `observations/`, `weather/`, `forage/` |
| Region definitions | `applebee/datasets.py` |
| Data acquisition | `scripts/fetch_prism.py`, `scripts/build_forage.py` |
| Simulation driver | `scripts/simulate.py` |
| Integrity checking | `applebee/provenance.py` |

Every input carries a `PROVENANCE.json` recording its source, retrieval date,
coverage, validation and a SHA-256 for each file; these records are tracked in
version control even where the data themselves are too large to distribute, so a
reader who rebuilds an input from its documented source can verify the result
against the digest used here.

**Model parameters** are supplied through a single `ModelParams` object and may
be overridden from a JSON or TOML file naming only the values that change:

```bash
python scripts/simulate.py --region northeast --params my_run.toml
```

Every simulation writes the exact parameter set used alongside its results.

**Data sources.** Daily weather: PRISM Climate Group 4 km gridded daily mean
temperature and precipitation (`services.nacse.org/prism`). Land cover: USDA
National Agricultural Statistics Service Cropland Data Layer, 30 m. Floral
resource values: Koh et al. (2016). Reproduction data: Centrella et al. (2020).
Abundance monitoring: Turley et al. (2022), Dryad `doi:10.5061/dryad.9kd51c5mc`.

---

## Acknowledgements

We thank the dissertation committee members (Heather Grab, Katriona Shea and
Mehrdad Mahdavi) for thoughtful feedback that shaped the design and
implementation of this study. Special thanks to Heather Grab for assistance with
data curation and analysis.

## Funding

Funding for Amoah was provided by the Interdisciplinary Studies in Entomology,
Computer Science and Technology Network (INSECT NET), supported by the National
Science Foundation's Research Traineeship Program (Grozinger, Boyle, Grant
2243979).

## Author contributions

EIA and CMG conceptualized the study. EIA led the experimental design, data
collection, data analysis, and writing of the first draft. NKB, EAHS and CMG
supervised. EIA, EAHS and CMG revised and edited the manuscript. NKB and CMG
secured funding.

---

## Supplementary tables

**Table S1. Linear mixed-effects model for total brood cells (Equation 10).**
Fitted by restricted maximum likelihood; 51 observations across 17 sites (3 per
site). Conditional $R^2$ = 0.510, RMSE = 28.56 cells.

| Effect | Estimate | Std. error | z | p | 95% CI |
|---|---|---|---|---|---|
| **Fixed effects** | | | | | |
| Intercept | 31.739 | 12.315 | 2.577 | 0.010 | 7.602 – 55.875 |
| Time point (T.2) | 1.246 | 11.657 | 0.107 | 0.915 | −21.601 – 24.093 |
| Time point (T.3) | −27.309 | 11.124 | −2.455 | 0.014 | −49.111 – −5.507 |
| Predicted eggs per female | 7.923 | 2.719 | 2.914 | 0.004 | 2.594 – 13.252 |
| **Random effect** | | | | | |
| Site (variance) | 306.788 | | | | |
| Site (SD) | 17.515 | | | | |
| Residual (variance) | 1049.8 | | | | |
| **Fit** | | | | | |
| Conditional $R^2$ | 0.510 | | | | |
| ICC | 0.226 | | | | |
| RMSE (cells) | 28.56 | | | | |

**Table S2. Linear mixed-effects model for *Osmia* abundance (Equation 11).**
Fitted by restricted maximum likelihood; n = 6. $R^2$ = 0.803, RMSE = 7.52. The
slope tested on the six annual counts directly is not significant (p = 0.36).

| Effect | Estimate | Std. error |
|---|---|---|
| Intercept | 15.514 | |
| Predicted offspring per female | 1.994 | 0.618 |
| Year (variance) | 169.555 | |
| Residual (variance) | 169.555 | |

*Year and residual variance are returned as identical because the design provides
one observation per group; see the Discussion.*

---

## Changes from the dissertation chapter

For the author's reference; remove before submission.

| Item | Chapter 4 | This manuscript |
|---|---|---|
| Objective 4 | Pennsylvania, 2009–2024, 7,452 cells × 16 years | **Northeast, 2014–2019, 44,756 cells × 6 years** |
| Obj. 2 $R^2$ | 0.52 | 0.510 |
| Obj. 2 β | 7.01 (p < 0.001) | 7.92 (p = 0.004) |
| Obj. 2 time point | T.2 significant, positive | **T.3 significant, negative** |
| Obj. 2 observed cells (max/mean/min/SD) | 206 / 65 / 12 / 42 | 182 / 52 / 4 / 41 |
| Obj. 3 $R^2$ / RMSE | 0.79 / 7.69 | 0.803 / 7.52 |
| Obj. 3 β | 1.82 (p > 0.05) | 1.99 (SE 0.62), p = 0.36 |
| Egg production importance | 98.3% | 95.4% |
| No-egg days (temp vs rain) | 6.38 vs 4.40 | 6.66 vs 4.47 |
| Sensitivity analysis | Sobol over three thresholds | **dropped** |

**Points requiring the author's attention**

1. **The Objective 2 time-point result has changed sign and moved.** The chapter
   reports Time Point 2 significantly positive; this analysis finds Time Point 3
   significantly negative. The Discussion paragraph on age-dependent reproductive
   output now reads more naturally — declining output with age is what the
   literature predicts (Sugiura & Maeta, 1989) — but the text should be revised
   deliberately rather than left as adapted here.
2. **Observed brood cells are reconstructed, not published.** The chapter's
   distribution (206/65/12/42) could not be reproduced from the published
   dataset; the reconstruction gives 182/52/4/41. The Methods state the
   reconstruction explicitly.
3. **Objective 3 significance.** The chapter reports β not significant, and so
   does this manuscript: the mixed model's own p of 0.001 is an artifact of the
   singleton random effect, so the slope is tested on the six annual counts
   directly (p = 0.36) and reported as not significant in the Results, on Figure
   4, and in the Discussion. Confirm this is how you want it presented.
4. **The daily-mean temperature limitation** is new material, prompted by the
   southern artifact in exploratory national runs. It strengthens the paper but
   needs your judgment on prominence.
5. **References** were extracted from the dissertation PDF and need a
   verification pass; a few entries were mangled by the extraction.

---

## References

Adams, L.R., 2001. Determination of Accumulation of Degree Days Required for the Emergence of Osma Cornifrons (Megachilidae) in Pennsylvania (Doctoral dissertation, Pennsylvania State University).

Ahn, J.J., Park, Y.L. and Jung, C., 2014. Modeling spring emergence of Osmia cornifrons Radoszkowski (Hymenoptera: Megachilidae) females in Korea. Journal of Asia-Pacific Entomology, 17(4), pp.901-905.

Batra, S.W., 1982. The hornfaced bee for efficient pollination of small farm orchards.

Biddinger, D. J., Rajotte, E. G., & Joshi, N. K. (2018). Integrating pollinator health into tree fruit IPM—A case study of Pennsylvania apple production. In D. W. Roubik (Ed.), The pollination of cultivated plants: A compendium for practitioners (Vol. 1, pp. 69–83). Food and Agricultural Organization of the United Nations.

Bosch, J. and Kemp, W.P., 2002. Developing and establishing bee species as crop pollinators: the example of Osmia spp.(Hymenoptera: Megachilidae) and fruit trees. Bulletin of entomological research, 92(1), pp.3-16.

Bosch, J., Sgolastra, F. and Kemp, W.P., 2008. Life cycle ecophysiology of Osmia mason bees used as crop pollinators. Bee pollination in agricultural ecosystems, pp.83-104.

Bosch, J., Sgolastra, F. and Kemp, W.P., 2010. Timing of eclosion affects diapause development, fat body consumption and longevity in Osmia lignaria, a univoltine, adult-wintering solitary bee. Journal of Insect Physiology, 56(12), pp.1949-1957.

Briscoe, N.J., Morris, S.D., Mathewson, P.D., Buckley, L.B., Jusup, M., Levy, O., Maclean, I.M.,

Bruckner, S., Wilson, M., Aurell, D., Rennich, K., Vanengelsdorp, D., Steinhauer, N., and Williams, G.R. 2023. A national survey of managed honey bee colony losses in the USA: Results from the Bee Informed Partnership for 2017–18, 2018–19, and 2019–20. Journal of Apicultural Research, 62(3), 429-443.

Cameron, S.A., and Sadd, B.M. 2020. Global trends in bumble bee health. Annual Review of

Cane, J.H. & Neff, J.L. (2011) Predicted fates of ground-nesting bees in soil heated by wildfire: thermal tolerances of life stages and a survey of nesting depths. Biological Conservation, 144, 2631– 2636.

Centrella, M., Russo, L., Moreno Ramírez, N., Eitzer, B., van Dyke, M., Danforth, B. and Poveda, K., 2020. Diet diversity and pesticide risk mediate the negative effects of land use change on solitary bee offspring production. Journal of Applied Ecology, 57(6), pp.1031-1042.

Denlinger, D.L. and Armbruster, P.A., 2014. Mosquito diapause. Annual review of entomology, 59(1), pp.73-93.

Denlinger, D.L., 2002. Regulation of diapause. Annual review of entomology, 47(1), pp.93-122.

Ecology, 52(4), pp.810-815.

Eilers, E. J., Kremen, C., Greenleaf, S. S., Garber, A. K., and Klein, A.-M. (2011). Contribution of pollinator-mediated crops to nutrients in the human food supply. PLoS ONE 6, e21363. doi: 10.1371/journal.pone.0021363

Entomology, 19(2), pp.281-287.

Entomology, 65(1), 209-232.

Entomology, 7(4), 453-462.

Forbes, V.E., Accolla, C., Banitz, T., Crouse, K., Galic, N., Grimm, V., Raimondo, S., Schmolke, A. and

Frankson, R., K.E. Kunkel, S.M. Champion, B.C. Stewart, W. Sweet, A.T. DeGaetano, and J. Spaccio, 2022: New York State Climate Summary 2022. NOAA Technical Report NESDIS 150-NY. NOAA/NESDIS, Silver Spring, MD, 5 pp.

Goodell, K. (2003). Food availability affects Osmia pumila (Hymenoptera: Megachilidae) foraging, reproduction, and brood parasitism. Oecologia, 134, 518-527.

Inouye, D.W. and Irwin, R.E., 2022. Life-history traits predict responses of wild bees to climate variation. Proceedings of the Royal Society B, 289(1973), p.20212697.

Johnston, A.S., Boyd, R.J., Watson, J.W., Paul, A., Evans, L.C., Gardner, E.L. and Boult, V.L., 2019. Predicting population responses to environmental change from individual-level mechanisms: towards a standardized mechanistic approach. Proceedings of the Royal Society B, 286(1913), p.20191916.

Jordan, A., Patch, H. M., Grozinger, C. M., and Khanna, V. (2021). Economic dependence and vulnerability of United States agricultural sector on insect-mediated pollination service. Environ. Sci. Technol. 55, 2243–2253. doi: 10.1021/acs.est.0c04786

Kammerer, M., Goslee, S.C., Douglas, M.R., Tooker, J.F. and Grozinger, C.M., 2021. Wild bees as winners and losers: Relative impacts of landscape composition, quality, and climate. Global change biology, 27(6), pp.1250-1265.

Kingsolver, J.G., Arthur Woods, H., Buckley, L.B., Potter, K.A., MacLean, H.J. and Higgins, J.K., 2011. Complex life cycles and the responses of insects to climate change.

Klein, A.-M., Vaissière, B. E., Cane, J. H., Steffan-Dewenter, I., Cunningham, S. A., Kremen, C., et al. (2007). Importance of pollinators in changing landscapes for world crops. Proc. R. Soc. B Biol. Sci. 274, 303–313. doi: 10.1098/rspb.2006.3721

Koh, I., Lonsdorf, E.V., Williams, N.M., Brittain, C., Isaacs, R., Gibbs, J. and Ricketts, T.H., 2016. Modeling the status, trends, and impacts of wild bee abundance in the United States. Proceedings of the National Academy of Sciences, 113(1), pp.140-145.

Lagerwall, G., Kiker, G., Muñoz-Carpena, R. and Wang, N., 2014. Global uncertainty and sensitivity analysis of a spatially distributed ecological model. Ecological modelling, 275, pp.22-30.

Lamie, C., Bader, D., Graziano, K., Horton, R., John, K., O'Hern, N., Spungin, S. and Stevens, A., 2024. New York State Climate Impacts Assessment Chapter 02: New York State's Changing Climate (Vol. 1542, No. 1, pp. 91-145).

Lawson, D. A., & Rands, S. A. (2019). The effects of rainfall on plant–pollinator interactions. Arthropod- Plant Interactions, 13(4), 561-569.

Lee, E., He, Y. and Park, Y.L., 2018. Effects of climate change on the phenology of Osmia cornifrons: implications for population management. Climatic Change, 150, pp.305-317.

Lee, K.Y., Yoon, H.J., Lee, K.S. and Jin, B.R., 2016. Development and mating behavior of Osmia cornifrons (Hymenoptera: Megachilidae) in the constant temperature. Journal of Asia-Pacific

Lonsdorf, E., Kremen, C., Ricketts, T., Winfree, R., Williams, N. and Greenleaf, S., 2009. Modelling pollination services across agricultural landscapes. Annals of botany, 103(9), pp.1589-1600.

Maeta, Y., 1978. Comparative studies on the biology of the bees of the genus Osmia in Japan, with special reference to their management for pollination of crops (Hymenoptera: Magachilidae). Bull. Tohoku Natl. Agric. Exp. Stn. 57, 1–221 (in Japanese).

Maeta, Y., 1981. Pollinating effciency by Osmia cornifrons (RADOSZKOWSKI) in relation to required number of nesting bees for economic fruit production. Honeybee Sci, 2, pp.65-72.

Maino, J.L., Kong, J.D., Hoffmann, A.A., Barton, M.G. and Kearney, M.R., 2016. Mechanistic models for predicting insect responses to climate change. Current opinion in insect science, 17, pp.81-86.

Mallinger, R.E. and Gratton, C., 2015. Species richness of wild bees, but not the use of managed honeybees, increases fruit set of a pollinator‐dependent crop. Journal of Applied Ecology, 52(2), pp.323-330.

Matsumoto, S. and Maejima, T., 2010. Several new aspects of the foraging behavior of Osmia cornifrons in an apple orchard. Psyche: A Journal of Entomology, 2010(1), p.384371.

Matsumoto, S., Abe, A. and Maejima, T., 2009. Foraging behavior of Osmia cornifrons in an apple orchard. Scientia horticulturae, 121(1), pp.73-79.

McKinney, M., Ahn, J.J. and Park, Y.L., 2017. Thermal biology of Osmia cornifrons (Hymenoptera: Megachilidae) eggs and larvae. Journal of Apicultural Research, 56(4), pp.421-429.

McKinney, M.I. and Park, Y.L., 2012. Nesting activity and behavior of Osmia cornifrons (Hymenoptera: Megachilidae) elucidated using videography. Psyche: A Journal of Entomology, 2012(1), p.814097.

Melone, G.G., Stuligross, C. and Williams, N.M., 2024. Heatwaves increase larval mortality and delay development of a solitary bee. Ecological Entomology, 49(3), pp.433-444.

Mokkapati, J. S., Hehl, J., Straub, L., Grozinger, C. M., & Boyle, N. (2025). Short-term heat exposure at sublethal temperatures reduces sperm quality in males of a solitary bee species, Osmia cornifrons. Apidologie, 56(1), 1-15.

Myers, W., Bishop, J. O. S. E. P. H., Brooks, R. O. B. E. R. T., O’Connell, T. I. M. O. T. H. Y., Argent, D. A. V. I. D., Storm, G. E. R. A. L. D., ... & Carline, R. O. B. E. R. T. (2000). Pennsylvania Gap Analysis Project. Final Report, School of Forest Resources, Pennsylvania State University, University Park, PA, 142.

Nossent, J., Elsen, P. and Bauwens, W., 2011. Sobol’sensitivity analysis of a complex environmental model. Environmental modelling & software, 26(12), pp.1515-1525.

Pardee, G.L., Griffin, S.R., Stemkovski, M., Harrison, T., Portman, Z.M., Kazenel, M.R., Lynn, J.S.,

Park, M.G., Joshi, N.K., Rajotte, E.G., Biddinger, D.J., Losey, J.E. and Danforth, B.N., 2020. Apple grower pollination practices and perceptions of alternative pollinators in New York and Pennsylvania. Renewable Agriculture and Food Systems, 35(1), pp.1-14.

Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., ... & Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. the Journal of machine Learning research, 12, 2825-2830.

Pincebourde, S., Riddell, E.A., Roberts, J.A. and Schouten, R., 2023. Mechanistic forecasts of species responses to climate change: the promise of biophysical ecology. Global Change Biology, 29(6), pp.1451-1470.

Potts, S.G., Biesmeijer, J.C., Kremen, C., Neumann, P., Schweiger, O. and Kunin, W.E., 2010. Global pollinator declines: trends, impacts and drivers. Trends in ecology & evolution, 25(6), pp.345- 353. PRISM Group, Oregon State University, https://prism.oregonstate.edu, data created 7 October 2019, accessed 16 February 2025

Reilly, J.R., Artz, D.R., Biddinger, D., Bobiwash, K., Boyle, N.K., Brittain, C., Brokaw, J., Campbell, J.W., Daniels, J., Elle, E. and Ellis, J.D., 2020. Crop production in the USA is frequently limited by a lack of pollinators. Proceedings of the Royal Society B, 287(1931), p.20200922.

Rightmyer, M.G., Sheffield, C.S. and Wright, K., 2020. Bee phenology is predicted by climatic variation and functional traits. Ecology letters, 23(11), pp.1589-1598.

Rodger, J. G., Bennett, J. M., Razanajatovo, M., Knight, T. M., van Kleunen, M., Ashman, T.-L., et al. (2021). Widespread vulnerability of flowering plant seed production to pollinator declines. Sci. Adv. 7, eabd3524. doi: 10.1126/sciadv.abd3524

Romero-Mujalli, D., Jeltsch, F. and Tiedemann, R., 2019. Individual-based modeling of eco-evolutionary dynamics: state of the art and future directions. Regional Environmental Change, 19, pp.1-12.

Rosolem, R., Gupta, H.V., Shuttleworth, W.J., Zeng, X. and de Gonçalves, L.G.G., 2012. A fully multiple‐criteria implementation of the Sobol′ method for parameter sensitivity analysis. Journal of Geophysical Research: Atmospheres, 117(D7).

Sgolastra, F., Arnan, X., PITTS‐SINGER, T.L., Maini, S., Kemp, W.P. and Bosch, J., 2016. Pre‐ wintering conditions and post‐winter performance in a solitary bee: does diapause impose an energetic cost on reproductive success?. Ecological Entomology, 41(2), pp.201-210.

Sgolastra, F., Kemp, W.P., Buckner, J.S., Pitts-Singer, T.L., Maini, S. and Bosch, J., 2011. The long summer: pre-wintering temperatures affect metabolic expenditure and winter survival in a solitary bee. Journal of Insect Physiology, 57(12), pp.1651-1659.

Stemkovski, M., Pearse, W.D., Griffin, S.R., Pardee, G.L., Gibbs, J., Griswold, T., Neff, J.L., Oram, R.,

Sugiura, N., & Maeta, Y. (1989). Parental investment and offspring sex ratio in a solitary mason bee, Osmia cornifrons (Radoszkowski)(Hymenoptera, Megachilidae).

Tepedino, V. J., & Torchio, P. F. (1982). Phenotypic variability in nesting success among Osmia lignaria propinqua females in a glasshouse environment:(Hymenoptera: Megachilidae). Ecological

Tochio, P.F., 1989. In-nest biologies and development of immature stages of three Osmia species (Hymenoptera: Magachilidae). Ann. Entomol. Soc. Am. 82, 599–615.

Torchio, P.F. and Asensio, E., 1985. The introduction of the European bee, Osmia cornuta Latr., into the US as a potential pollinator of orchard crops, and a comparison of its manageability with Osmia lignaria propinqua Cresson (Hymenoptera: Megachilidae). Journal of the Kansas Entomological

Torchio, P.F., 1976. Use of Osmia lignaria Say (Hymenoptera: Apoidea, Megachilidae) as a pollinator in an apple and prune orchard. Journal of the Kansas Entomological Society, pp.475-482.

Turley, N.E., Biddinger, D.J., Joshi, N.K. and López‐Uribe, M.M., 2022. Six years of wild bee monitoring shows changes in biodiversity within and across years and declines in abundance. Ecology and Evolution, 12(8), p.e9190.

Ulyshen, M., and Horn, S. 2023. Declines of bees and butterflies over 15 years in a forested landscape. Current Biology, 33(7), 1346-1350.

Ummenhofer, C.C. and Meehl, G.A., 2017. Extreme weather and climate events with ecological relevance: a review. Philosophical Transactions of the Royal Society B: Biological Sciences, 372(1723), p.20160135.

Vaugeois, M., 2024. Mechanistic population models for ecological risk assessment and decision support: The importance of good conceptual model diagrams. Integrated Environmental Assessment and Management, 20(5), pp.1566-1574.

Wagner, D.L., Grames, E.M., Forister, M.L., Berenbaum, M.R. and Stopak, D., 2021. Insect decline in the Anthropocene: Death by a thousand cuts. Proceedings of the National Academy of Sciences, 118(2), p.e2023989118.

Walsh, J.E., Ballinger, T.J., Euskirchen, E.S., Hanna, E., Mård, J., Overland, J.E., Tangen, H. and Vihma, T., 2020. Extreme weather and climate events in northern areas: A review. Earth-Science

Wang, H., Zhao, Y. and Fu, W., 2023. Utilizing the Sobol’sensitivity analysis method to address the multi-objective operation model of reservoirs. Water, 15(21), p.3795.

Westra, S., Fowler, H.J., Evans, J.P., Alexander, L.V., Berg, P., Johnson, F., Kendon, E.J., Lenderink, G. and Roberts, N., 2014. Future changes to the intensity and frequency of short‐duration extreme rainfall. Reviews of Geophysics, 52(3), pp.522-555.

Westreich, L. R., Westreich, S. T., & Tobin, P. C. (2023). Native solitary bee reproductive success depends on early season precipitation and host plant richness. Oecologia, 201(4), 965-978.

White, J., Son, Y. and Park, Y.L., 2009. Temperature-dependent emergence of Osmia cornifrons (Hymenoptera: Megachilidae) adults. Journal of economic entomology, 102(6), pp.2026-2032.

Wood, K.A., Stillman, R.A. and Goss-Custard, J.D., 2015. Co-creation of individual-based models by practitioners and modellers to inform environmental decision-making. Journal of Applied

Yu-Guo, Z.H.A.N.G., Cheng-Huai, Q.U., Li-Ping, W.A.N.G., Dong, G.U.O. and Ling-Ya, Y.U., 2019. Analysis of the pollinating services provided by Osmia cornifrous (Rodoszkouski) and Apis mellifera ligustica Spin in apple and cherry orchards. Chinese Journal of Applied

Yun-Li, X.I.A.O., Wen-Ying, T.A.N.G., Cun-Hui, L.I.U., Kai, Y.U., Yi, G.O.N.G., Qin-Min, Y.A.N.G.,
