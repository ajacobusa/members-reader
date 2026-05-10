from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUTPUT = "DAT_Study_Plan_2026.pdf"

# ── Colour palette ──────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1B2A4A")
TEAL   = colors.HexColor("#2A7B8C")
GOLD   = colors.HexColor("#D4A017")
LIGHT  = colors.HexColor("#EEF4F7")
WHITE  = colors.white
GREY   = colors.HexColor("#F5F5F5")
MID    = colors.HexColor("#CCDEEA")

# ── Styles ───────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

sTitle = S("sTitle", fontSize=28, textColor=WHITE, alignment=TA_CENTER,
           fontName="Helvetica-Bold", leading=34)
sSubtitle = S("sSubtitle", fontSize=13, textColor=GOLD, alignment=TA_CENTER,
              fontName="Helvetica-Bold", leading=18)
sMeta = S("sMeta", fontSize=10, textColor=WHITE, alignment=TA_CENTER,
          fontName="Helvetica", leading=14)

sPhaseHead = S("sPhaseHead", fontSize=14, textColor=WHITE, fontName="Helvetica-Bold",
               leading=18, alignment=TA_LEFT)
sSectionHead = S("sSectionHead", fontSize=11, textColor=NAVY, fontName="Helvetica-Bold",
                 leading=15, spaceAfter=4)
sBody = S("sBody", fontSize=9.5, textColor=NAVY, fontName="Helvetica",
          leading=14, spaceAfter=2)
sBullet = S("sBullet", fontSize=9.5, textColor=NAVY, fontName="Helvetica",
            leading=14, leftIndent=12, bulletIndent=0, spaceAfter=1)
sTip = S("sTip", fontSize=8.5, textColor=colors.HexColor("#4A4A4A"),
         fontName="Helvetica-Oblique", leading=12)
sCell = S("sCell", fontSize=8.5, textColor=NAVY, fontName="Helvetica", leading=12)
sCellBold = S("sCellBold", fontSize=8.5, textColor=NAVY, fontName="Helvetica-Bold", leading=12)
sCellWhite = S("sCellWhite", fontSize=8.5, textColor=WHITE, fontName="Helvetica-Bold",
               leading=12, alignment=TA_CENTER)


def hline():
    return HRFlowable(width="100%", thickness=1, color=MID, spaceAfter=6, spaceBefore=6)


def phase_header(label, subtitle, color=NAVY):
    table = Table([[Paragraph(label, sPhaseHead)],
                   [Paragraph(subtitle, S("ps", fontSize=9, textColor=GOLD,
                                          fontName="Helvetica", leading=12))]],
                  colWidths=[6.5*inch])
    table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), color),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",(0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return table


def day_table(rows, header_bg=TEAL):
    """rows: list of (date, day_num, topic) tuples."""
    data = [[Paragraph("Date", sCellWhite),
             Paragraph("Day", sCellWhite),
             Paragraph("Topic / Focus", sCellWhite)]]
    for i, (date, day, topic) in enumerate(rows):
        row_bg = GREY if i % 2 == 0 else WHITE
        data.append([
            Paragraph(date, sCellBold),
            Paragraph(str(day), sCell),
            Paragraph(topic, sCell),
        ])
    t = Table(data, colWidths=[1.3*inch, 0.5*inch, 4.7*inch])
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  header_bg),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D0D0")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [GREY, WHITE]),
    ]
    t.setStyle(TableStyle(style))
    return t


def two_col_table(left_items, right_items, left_head, right_head):
    data = [[Paragraph(left_head, sCellWhite), Paragraph(right_head, sCellWhite)]]
    max_len = max(len(left_items), len(right_items))
    for i in range(max_len):
        l = Paragraph(f"• {left_items[i]}", sCell) if i < len(left_items) else Paragraph("", sCell)
        r = Paragraph(f"• {right_items[i]}", sCell) if i < len(right_items) else Paragraph("", sCell)
        data.append([l, r])
    t = Table(data, colWidths=[3.25*inch, 3.25*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("BACKGROUND",    (0, 1), (-1, -1), LIGHT),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ── Cover block ──────────────────────────────────────────────────────────────
def cover_block():
    cover = Table(
        [[Paragraph("DAT Dental Exam", sTitle)],
         [Paragraph("Complete Study Plan", sSubtitle)],
         [Spacer(1, 6)],
         [Paragraph("Exam Date: June 24, 2026  |  Study Start: May 10, 2026", sMeta)],
         [Paragraph("45 Days · 6 Phases · Full Review Week", sMeta)]],
        colWidths=[6.5*inch]
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",  (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING",(0,0), (-1,-1), 18),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",(0, 0), (-1, -1), 20),
    ]))
    return cover


# ── Build story ──────────────────────────────────────────────────────────────
def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.6*inch,
        bottomMargin=0.6*inch,
        title="DAT Study Plan 2026",
        author="Anoop Jacob",
    )
    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.append(cover_block())
    story.append(Spacer(1, 16))

    # ── Overview summary table ────────────────────────────────────────────────
    story.append(Paragraph("Plan Overview", sSectionHead))
    overview = [
        [Paragraph("Phase", sCellWhite), Paragraph("Dates", sCellWhite),
         Paragraph("Subject", sCellWhite), Paragraph("Days", sCellWhite)],
        [Paragraph("1", sCell), Paragraph("May 10 – May 21", sCell),
         Paragraph("Biology", sCell), Paragraph("12", sCell)],
        [Paragraph("2", sCell), Paragraph("May 22 – May 31", sCell),
         Paragraph("General Chemistry", sCell), Paragraph("10", sCell)],
        [Paragraph("3", sCell), Paragraph("June 1 – June 6", sCell),
         Paragraph("Organic Chemistry", sCell), Paragraph("6", sCell)],
        [Paragraph("4", sCell), Paragraph("June 7 – June 11", sCell),
         Paragraph("Perceptual Ability Test (PAT)", sCell), Paragraph("5", sCell)],
        [Paragraph("5", sCell), Paragraph("June 12 – June 16", sCell),
         Paragraph("Quantitative Reasoning &amp; Reading Comprehension", sCell), Paragraph("5", sCell)],
        [Paragraph("6", sCell), Paragraph("June 17 – June 23", sCell),
         Paragraph("Final Review Week", sCell), Paragraph("7", sCell)],
        [Paragraph("EXAM", sCellBold), Paragraph("June 24, 2026", sCellBold),
         Paragraph("DAT Dental Admission Test", sCellBold), Paragraph("—", sCellBold)],
    ]
    ov_t = Table(overview, colWidths=[0.6*inch, 1.7*inch, 3.5*inch, 0.7*inch])
    ov_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  TEAL),
        ("BACKGROUND",    (0, 7), (-1, 7),  GOLD),
        ("ROWBACKGROUNDS",(0, 1), (-1, 6),  [GREY, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(ov_t)
    story.append(Spacer(1, 14))

    # ── Daily schedule block ──────────────────────────────────────────────────
    story.append(Paragraph("Recommended Daily Schedule", sSectionHead))
    ds = [
        [Paragraph("Block", sCellWhite), Paragraph("Duration", sCellWhite),
         Paragraph("Activity", sCellWhite)],
        [Paragraph("Morning", sCell), Paragraph("2 hours", sCell),
         Paragraph("New content — read notes, watch videos, take structured notes", sCell)],
        [Paragraph("Afternoon", sCell), Paragraph("2 hours", sCell),
         Paragraph("Practice questions on that day's topic; review all incorrect answers", sCell)],
        [Paragraph("Evening", sCell), Paragraph("30 min", sCell),
         Paragraph("Flashcard review (Anki / paper) — weak spots and formula refresh", sCell)],
    ]
    dst = Table(ds, colWidths=[1.1*inch, 1.0*inch, 4.4*inch])
    dst.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [GREY, WHITE, LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(dst)
    story.append(Spacer(1, 18))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — BIOLOGY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 1 — Biology", "May 10 – May 21  ·  12 Days", TEAL))
    story.append(Spacer(1, 8))

    bio_days = [
        ("May 10",  1,  "Cell structure, organelles (nucleus, mitochondria, ER, Golgi, lysosomes), membrane transport (passive, active, osmosis)"),
        ("May 11",  2,  "Cell division — mitosis (PMAT) & meiosis I/II; crossing over, nondisjunction, ploidy"),
        ("May 12",  3,  "Molecular biology — DNA structure, semi-conservative replication; transcription, RNA processing; translation & the genetic code"),
        ("May 13",  4,  "Mendelian genetics — dominant/recessive, Punnett squares, dihybrid crosses, sex-linked traits, codominance, incomplete dominance"),
        ("May 14",  5,  "Molecular genetics — gene regulation (operons), mutations (point, frameshift), chromosomal abnormalities, cancer biology"),
        ("May 15",  6,  "Evolution — natural selection, Hardy-Weinberg, speciation, phylogenetics; Ecology — food webs, biomes, population dynamics"),
        ("May 16",  7,  "REVIEW DAY #1 — Re-read notes Days 1–6; complete 30+ practice questions; make error log"),
        ("May 17",  8,  "Anatomy I — musculoskeletal (bone types, muscle contraction, sliding filament); circulatory (heart anatomy, cardiac cycle, ABO blood); respiratory (lung mechanics, gas exchange)"),
        ("May 18",  9,  "Anatomy II — digestive (enzymes, absorption, liver function); excretory (nephron anatomy, filtration, urine formation); nervous system (neuron, action potential, CNS/PNS, reflex arc)"),
        ("May 19", 10,  "Anatomy III — endocrine (hormones, feedback loops, glands); immune system (innate vs adaptive, B/T cells, antibodies); reproductive systems (gametogenesis, hormonal cycle)"),
        ("May 20", 11,  "Developmental biology (embryonic layers, organogenesis); Taxonomy (Linnaean classification, 3 domains, 6 kingdoms, key phylla)"),
        ("May 21", 12,  "FULL BIOLOGY REVIEW — Timed practice section (40 Q / 30 min); review all missed; update formula/term cheat sheet"),
    ]
    story.append(day_table(bio_days))
    story.append(Spacer(1, 8))

    story.append(Paragraph("High-Yield Biology Topics", sSectionHead))
    story.append(two_col_table(
        ["Cell organelle functions", "Mitosis vs meiosis stages", "DNA replication enzymes",
         "Genetic inheritance patterns", "Hardy-Weinberg equilibrium",
         "Nephron filtration steps", "Action potential phases"],
        ["Cardiac conduction system", "Hormones & their glands", "Immune cell types & roles",
         "Enzyme kinetics (Km, Vmax)", "Muscle contraction cascade",
         "Embryonic germ layers & derivatives", "Taxonomy domains & kingdoms"],
        "Content Area", "Content Area"
    ))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — GENERAL CHEMISTRY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 2 — General Chemistry", "May 22 – May 31  ·  10 Days", colors.HexColor("#1A6B4A")))
    story.append(Spacer(1, 8))

    gchem_days = [
        ("May 22", 13, "Atomic structure (quantum numbers, electron config, orbital shapes); periodic trends (EN, atomic radius, IE, EA); bonding — ionic, covalent, VSEPR, hybridization"),
        ("May 23", 14, "Stoichiometry — molar mass, limiting reagents, percent yield; balancing equations; reaction types (combination, decomposition, single/double displacement, combustion)"),
        ("May 24", 15, "Gases — ideal gas law (PV=nRT), Dalton's partial pressures, Graham's effusion law, kinetic molecular theory, real gas deviations (van der Waals)"),
        ("May 25", 16, "Liquids & solids — IMFs (H-bond, dipole, London), phase diagrams, phase changes; solutions — molarity, molality, colligative properties (BP elevation, FP depression, osmotic pressure)"),
        ("May 26", 17, "Thermodynamics — ΔH, ΔS, ΔG = ΔH – TΔS; Hess's law; standard enthalpies of formation; calorimetry (q = mcΔT)"),
        ("May 27", 18, "Chemical equilibrium — Kp & Kc, reaction quotient Q, Le Chatelier's principle; solubility product Ksp, common ion effect"),
        ("May 28", 19, "Acids & bases — Bronsted-Lowry, Ka/Kb, pH/pOH calculations, strong vs weak acids, buffer systems, Henderson-Hasselbalch, titration curves"),
        ("May 29", 20, "Electrochemistry — oxidation states, balancing redox (half-reaction), galvanic vs electrolytic cells, standard cell potential E°cell, Nernst equation, Faraday's law"),
        ("May 30", 21, "Kinetics — reaction rates, rate laws, integrated rate laws (0th/1st/2nd order), half-life; Nuclear chemistry — decay types (α, β, γ), half-life calculations, fission vs fusion"),
        ("May 31", 22, "FULL GEN CHEM REVIEW — Timed practice section (30 Q / 30 min); review mistakes; update equation sheet"),
    ]
    story.append(day_table(gchem_days, header_bg=colors.HexColor("#1A6B4A")))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Key Equations to Memorize", sSectionHead))
    eqs = [
        [Paragraph("Equation", sCellWhite), Paragraph("Formula", sCellWhite), Paragraph("Use", sCellWhite)],
        [Paragraph("Ideal Gas Law", sCell), Paragraph("PV = nRT", sCellBold), Paragraph("Gas problems", sCell)],
        [Paragraph("Gibbs Free Energy", sCell), Paragraph("ΔG = ΔH – TΔS", sCellBold), Paragraph("Spontaneity", sCell)],
        [Paragraph("Henderson-Hasselbalch", sCell), Paragraph("pH = pKa + log([A-]/[HA])", sCellBold), Paragraph("Buffer pH", sCell)],
        [Paragraph("Nernst Equation", sCell), Paragraph("E = E° – (RT/nF)lnQ", sCellBold), Paragraph("Non-standard cell potential", sCell)],
        [Paragraph("Calorimetry", sCell), Paragraph("q = mcΔT", sCellBold), Paragraph("Heat transfer", sCell)],
        [Paragraph("First-order half-life", sCell), Paragraph("t₁/₂ = 0.693/k", sCellBold), Paragraph("Radioactive decay, kinetics", sCell)],
    ]
    eq_t = Table(eqs, colWidths=[1.8*inch, 2.3*inch, 2.4*inch])
    eq_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [GREY, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(eq_t)
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3 — ORGANIC CHEMISTRY
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 3 — Organic Chemistry", "June 1 – June 6  ·  6 Days", colors.HexColor("#7B2D8C")))
    story.append(Spacer(1, 8))

    orgo_days = [
        ("June 1",  23, "Nomenclature (IUPAC) for alkanes, alkenes, alkynes; functional groups identification; stereochemistry — chirality, R/S configuration, E/Z alkenes, Fischer projections, optical activity"),
        ("June 2",  24, "Substitution reactions — SN1 (carbocation, racemization) vs SN2 (backside attack, inversion); Elimination — E1 vs E2 (Zaitsev's rule); factors: substrate, nucleophile, solvent, temp"),
        ("June 3",  25, "Addition reactions — electrophilic addition to alkenes (Markovnikov), HX, H2O, X2, hydroboration; Aromaticity (Huckel's rule, EAS); NAS for benzene"),
        ("June 4",  26, "Carbonyl chemistry — aldehydes & ketones (nucleophilic addition, aldol, oxidation/reduction); carboxylic acids & derivatives (esters, amides, anhydrides, acyl substitution); amines (basicity, reactions)"),
        ("June 5",  27, "Lab techniques — extraction (acid-base), distillation (simple/fractional), recrystallization, chromatography (TLC, column); spectroscopy overview — IR (functional group ID), NMR (H environments), MS (molecular weight)"),
        ("June 6",  28, "FULL ORGO REVIEW — Timed practice section (15 Q / 20 min); draw out every major mechanism from memory; review stereochemistry problems"),
    ]
    story.append(day_table(orgo_days, header_bg=colors.HexColor("#7B2D8C")))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Reaction Mechanisms Cheat Sheet", sSectionHead))
    story.append(two_col_table(
        ["SN1 — tertiary substrate, polar protic, carbocation", "SN2 — primary substrate, polar aprotic, backside attack",
         "E1 — tertiary, high temp, weak base", "E2 — strong base, anti-periplanar geometry",
         "Electrophilic addition — Markovnikov rule", "EAS — activating vs deactivating groups"],
        ["Aldol condensation — enolate + carbonyl", "Ester hydrolysis — acid or base catalyzed",
         "Grignard reaction — carbon nucleophile", "Oxidation states — primary → aldehyde → acid",
         "Reduction — NaBH4 (ketones/aldehydes) vs LiAlH4 (all carbonyls)", "Diels-Alder — diene + dienophile → cyclohexene"],
        "Mechanism / Rule", "Mechanism / Rule"
    ))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4 — PAT
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 4 — Perceptual Ability Test (PAT)", "June 7 – June 11  ·  5 Days", colors.HexColor("#B05A00")))
    story.append(Spacer(1, 8))

    pat_days = [
        ("June 7",  29, "Aperture Passing (Keyhole) — visualize 3D objects passing through 2D cutouts; practice 60 items timed; learn elimination strategy"),
        ("June 8",  30, "View Recognition — orthographic projection; match top / front / end views to 3D object; practice drawing views from isometric diagrams"),
        ("June 9",  31, "Angle Discrimination — rank angles from smallest to largest; Paper Folding — track fold/punch positions mentally; 50 timed items each"),
        ("June 10", 32, "Cube Counting — count hidden cubes, track exposed faces; 3D Form Development (Pattern Folding) — fold flat nets into 3D boxes; identify correct assembled shape"),
        ("June 11", 33, "FULL PAT PRACTICE TEST — all 6 PAT subtypes timed (90 Q / 60 min); score & analyze weakest subtype; drill that subtype with 30 extra items"),
    ]
    story.append(day_table(pat_days, header_bg=colors.HexColor("#B05A00")))
    story.append(Spacer(1, 8))

    story.append(Paragraph("PAT Strategy Tips", sSectionHead))
    pat_tips = [
        "Aperture: check overall shape silhouette first — eliminate non-matches before testing orientation.",
        "View Recognition: always identify the top view first; it eliminates the most options.",
        "Angle Discrimination: use a reference angle (90°) to bucket choices, then rank within buckets.",
        "Paper Folding: trace one fold at a time; mark the punch dot relative to the fold line.",
        "Cube Counting: count systematically by layer (bottom → top); mark cubes as you go.",
        "Pattern Folding: identify which face must be opposite which, and eliminate impossible answers.",
        "Pacing: ~40 sec per item — skip and flag if stuck; return at the end.",
    ]
    for tip in pat_tips:
        story.append(Paragraph(f"• {tip}", sBullet))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 5 — QR & RC
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 5 — Quantitative Reasoning & Reading Comprehension",
                              "June 12 – June 16  ·  5 Days", colors.HexColor("#5C3A1E")))
    story.append(Spacer(1, 8))

    qr_days = [
        ("June 12", 34, "QR — Algebra: solving equations, inequalities, systems, quadratics; Word problems (rate, distance, work, mixture); Unit conversions & proportions"),
        ("June 13", 35, "QR — Probability & statistics (mean, median, mode, SD, combinations/permutations); Geometry (area, volume, Pythagorean theorem); Trigonometry basics (SOH-CAH-TOA)"),
        ("June 14", 36, "RC — Reading strategy: search-and-destroy vs read-all-first; identifying tone, main idea, inference questions; complete 2 timed passages with full review"),
        ("June 15", 37, "RC — 3 full timed passages (natural sciences format); review all incorrect; note recurring trap answer types"),
        ("June 16", 38, "FULL-LENGTH TIMED PRACTICE EXAM — all DAT sections under test conditions; log score by section; identify top-3 weak areas for final review week"),
    ]
    story.append(day_table(qr_days, header_bg=colors.HexColor("#5C3A1E")))
    story.append(Spacer(1, 8))

    story.append(Paragraph("QR Topics at a Glance", sSectionHead))
    story.append(two_col_table(
        ["Algebra — linear equations, systems, inequalities", "Quadratic equations & factoring",
         "Ratios, proportions, percentages", "Rate, distance, work problems",
         "Probability — independent & conditional events", "Combinations & permutations (nCr, nPr)"],
        ["Statistics — mean, median, mode, range, SD", "Geometry — area & perimeter of 2D shapes",
         "Volume & surface area of 3D solids", "Coordinate geometry — slope, midpoint, distance",
         "Trigonometry — SOH-CAH-TOA, unit circle basics", "Logarithms & exponent rules"],
        "Quantitative Reasoning Topic", "Quantitative Reasoning Topic"
    ))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 6 — FINAL REVIEW WEEK
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(phase_header("Phase 6 — Final Review Week", "June 17 – June 23  ·  7 Days", colors.HexColor("#8B0000")))
    story.append(Spacer(1, 8))

    review_days = [
        ("June 17", 39, "BIOLOGY REVIEW — High-yield only: cell division, genetics, organ systems, homeostasis. Re-read Feralis notes. 20 mixed practice questions."),
        ("June 18", 40, "GEN CHEM REVIEW — High-yield: acid/base, equilibrium, electrochemistry, thermodynamics. Run through equation sheet. 20 mixed practice questions."),
        ("June 19", 41, "ORGO REVIEW — Mechanisms cheat sheet from memory; SN1/SN2/E1/E2 decision tree; carbonyl reactions. 30-min PAT warm-up session."),
        ("June 20", 42, "QR & RC REVIEW — Drill weakest QR topic from practice exam; complete 1 timed RC passage; review answer strategies for both sections."),
        ("June 21", 43, "FULL-LENGTH PRACTICE TEST #2 — timed, exam-day conditions; simulate every break and transition exactly as on test day."),
        ("June 22", 44, "REVIEW TEST #2 RESULTS — focus only on weak areas flagged by test; no new material; consolidate formula sheet to one page; prepare test-day checklist."),
        ("June 23", 45, "LIGHT DAY — review formula sheet (30 min max); visualize exam-day routine; pack materials (ID, snacks, water); eat well; sleep by 10 PM."),
    ]
    story.append(day_table(review_days, header_bg=colors.HexColor("#8B0000")))
    story.append(Spacer(1, 12))

    # Exam Day box
    exam_data = [
        [Paragraph("EXAM DAY — June 24, 2026", S("ed", fontSize=13, textColor=WHITE,
                                                   fontName="Helvetica-Bold", leading=18, alignment=TA_CENTER))],
    ]
    exam_t = Table(exam_data, colWidths=[6.5*inch])
    exam_t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), GOLD),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
    ]))
    story.append(exam_t)
    story.append(Spacer(1, 6))

    exam_tips = [
        "Eat a real breakfast — avoid heavy or unfamiliar foods.",
        "Arrive at the testing center 30 minutes early with valid photo ID.",
        "Section order: Survey of Natural Sciences → PAT → Reading Comprehension → Quantitative Reasoning.",
        "Use scratch paper heavily during PAT and QR; show all work.",
        "Flag uncertain questions and return — never leave a question blank (no penalty).",
        "Trust the 45 days of preparation. Stay calm and pace yourself.",
    ]
    for tip in exam_tips:
        story.append(Paragraph(f"• {tip}", sBullet))
    story.append(Spacer(1, 16))

    # ═══════════════════════════════════════════════════════════════════════════
    # RESOURCES
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(hline())
    story.append(Paragraph("Recommended Study Resources", sSectionHead))
    resources = [
        [Paragraph("Resource", sCellWhite), Paragraph("Best Used For", sCellWhite), Paragraph("Priority", sCellWhite)],
        [Paragraph("Chad's Videos", sCell), Paragraph("Gen Chem & Orgo concept videos — best explanations available", sCell), Paragraph("★★★★★", sCell)],
        [Paragraph("Feralis Biology Notes", sCell), Paragraph("Highest-yield biology outline; covers ~95% of DAT bio content", sCell), Paragraph("★★★★★", sCell)],
        [Paragraph("Crack DAT PAT", sCell), Paragraph("Daily PAT drills; most realistic PAT practice online", sCell), Paragraph("★★★★★", sCell)],
        [Paragraph("DATBooster / Bootcamp", sCell), Paragraph("Full-length practice tests; question banks for all sections", sCell), Paragraph("★★★★★", sCell)],
        [Paragraph("Anki (DAT deck)", sCell), Paragraph("Spaced-repetition flashcards; bio + chem vocabulary", sCell), Paragraph("★★★★☆", sCell)],
        [Paragraph("Kaplan DAT Prep", sCell), Paragraph("Content review book; good for structured reading", sCell), Paragraph("★★★☆☆", sCell)],
        [Paragraph("Khan Academy", sCell), Paragraph("Free backup for gen chem and math concept review", sCell), Paragraph("★★★☆☆", sCell)],
    ]
    res_t = Table(resources, colWidths=[1.7*inch, 3.8*inch, 1.0*inch])
    res_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [GREY, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(res_t)
    story.append(Spacer(1, 12))

    # ── Score targets ─────────────────────────────────────────────────────────
    story.append(Paragraph("Target Scores (Competitive Range)", sSectionHead))
    scores = [
        [Paragraph("Section", sCellWhite), Paragraph("Competitive Score", sCellWhite), Paragraph("Top-Tier Score", sCellWhite)],
        [Paragraph("Biology", sCell), Paragraph("18–19", sCell), Paragraph("20+", sCell)],
        [Paragraph("General Chemistry", sCell), Paragraph("18–19", sCell), Paragraph("20+", sCell)],
        [Paragraph("Organic Chemistry", sCell), Paragraph("18–19", sCell), Paragraph("20+", sCell)],
        [Paragraph("Perceptual Ability Test", sCell), Paragraph("18–19", sCell), Paragraph("20+", sCell)],
        [Paragraph("Reading Comprehension", sCell), Paragraph("18–19", sCell), Paragraph("20+", sCell)],
        [Paragraph("Quantitative Reasoning", sCell), Paragraph("17–18", sCell), Paragraph("20+", sCell)],
        [Paragraph("Academic Average (AA)", sCellBold), Paragraph("19", sCellBold), Paragraph("21+", sCellBold)],
    ]
    sc_t = Table(scores, colWidths=[2.5*inch, 2.0*inch, 2.0*inch])
    sc_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  TEAL),
        ("BACKGROUND",    (0, 7), (-1, 7),  GOLD),
        ("ROWBACKGROUNDS",(0, 1), (-1, 6),  [GREY, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sc_t)
    story.append(Spacer(1, 10))

    story.append(hline())
    story.append(Paragraph(
        "Good luck — 45 days of consistent, focused work will get you there. You've got this.",
        S("final", fontSize=10, textColor=NAVY, fontName="Helvetica-Bold",
          alignment=TA_CENTER, leading=14)
    ))

    doc.build(story)
    print(f"PDF created: {OUTPUT}")


if __name__ == "__main__":
    build()
