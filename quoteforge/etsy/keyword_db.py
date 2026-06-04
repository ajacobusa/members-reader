"""Etsy keyword database for wall art niches."""

# Structure: niche -> {"high_volume": [], "mid_volume": [], "long_tail": [], "buyer_intent": []}
KEYWORD_DB: dict[str, dict[str, list[str]]] = {
    "Daughter Gifts": {
        "high_volume": [
            "daughter gift",
            "gift for daughter",
            "daughter wall art",
            "personalized daughter gift",
            "graduation gift daughter",
        ],
        "mid_volume": [
            "to my daughter print",
            "daughter birthday gift",
            "daughter from mom gift",
            "daughter bedroom decor",
            "inspirational daughter quote",
        ],
        "long_tail": [
            "personalized daughter graduation gift from mom",
            "to my daughter on her graduation wall art print",
            "custom quote print for daughters bedroom",
            "heartfelt gift for daughter graduating college",
            "mountain scenic daughter encouragement poster",
        ],
        "buyer_intent": [
            "daughter graduation gift ideas",
            "meaningful gifts for daughters",
            "personalized gifts for daughter from mom",
        ],
    },
    "Son Gifts": {
        "high_volume": [
            "son gift",
            "gift for son",
            "son wall art",
            "personalized son gift",
            "graduation gift son",
        ],
        "mid_volume": [
            "to my son print",
            "son birthday gift",
            "son from mom gift",
            "son from dad gift",
            "inspirational son quote",
        ],
        "long_tail": [
            "personalized son graduation gift from parents",
            "to my son on his wedding day wall art",
            "custom quote print for son from mom",
            "heartfelt gift for son going to college",
            "son military deployment framed print",
        ],
        "buyer_intent": [
            "son graduation gift ideas",
            "meaningful gifts for sons",
            "personalized gifts for son",
        ],
    },
    "Wife Gift": {
        "high_volume": [
            "wife gift",
            "gift for wife",
            "wife wall art",
            "anniversary gift wife",
            "wife birthday gift",
        ],
        "mid_volume": [
            "to my wife print",
            "wife valentine gift",
            "wife canvas print",
            "romantic gift wife",
            "wife decor bedroom",
        ],
        "long_tail": [
            "personalized anniversary gift for wife from husband",
            "to my wife on our anniversary wall art print",
            "romantic bedroom wall art gift for her",
            "heartfelt birthday gift for wife",
            "just because gift for wife wall art",
        ],
        "buyer_intent": [
            "unique anniversary gifts for wife",
            "meaningful wife birthday gift ideas",
            "romantic wall art for wife",
        ],
    },
    "Husband Gift": {
        "high_volume": [
            "husband gift",
            "gift for husband",
            "husband wall art",
            "anniversary gift husband",
            "husband birthday gift",
        ],
        "mid_volume": [
            "to my husband print",
            "husband valentine gift",
            "husband canvas print",
            "romantic gift husband",
            "husband man cave decor",
        ],
        "long_tail": [
            "personalized anniversary gift for husband from wife",
            "to my husband on our anniversary wall art print",
            "romantic man cave wall art gift for him",
            "sentimental birthday gift for husband",
            "husband office desk decor art print",
        ],
        "buyer_intent": [
            "unique anniversary gifts for husband",
            "thoughtful husband birthday gift ideas",
            "personalized wall art for husband",
        ],
    },
    "Mom Gift": {
        "high_volume": [
            "mom gift",
            "gift for mom",
            "mothers day gift",
            "personalized mom gift",
            "mom wall art",
        ],
        "mid_volume": [
            "to my mom print",
            "mom birthday gift",
            "mom from kids gift",
            "mama decor",
            "mother quote art",
        ],
        "long_tail": [
            "personalized mothers day gift from kids",
            "to my mom on mothers day wall art print",
            "custom quote print for mom from adult child",
            "heartfelt birthday gift for mom wall art",
            "mama bear family names print personalized",
        ],
        "buyer_intent": [
            "unique mothers day gift ideas",
            "meaningful gifts for mom from kids",
            "personalized wall art for mom",
        ],
    },
    "Dad Gift": {
        "high_volume": [
            "dad gift",
            "gift for dad",
            "fathers day gift",
            "personalized dad gift",
            "dad wall art",
        ],
        "mid_volume": [
            "to my dad print",
            "dad birthday gift",
            "dad from kids gift",
            "papa decor",
            "father quote art",
        ],
        "long_tail": [
            "personalized fathers day gift from kids",
            "to my dad on fathers day wall art print",
            "custom quote print for dad from adult child",
            "heartfelt birthday gift for dad wall art",
            "dad fishing lake house decor art print",
        ],
        "buyer_intent": [
            "unique fathers day gift ideas",
            "meaningful gifts for dad from kids",
            "personalized wall art for dad",
        ],
    },
    "Grandma Gift": {
        "high_volume": [
            "grandma gift",
            "nana gift",
            "gift for grandma",
            "grandchildren names print",
            "grandmother wall art",
        ],
        "mid_volume": [
            "personalized grandma gift",
            "nana wall art",
            "grandma birthday gift",
            "grandmother decor",
            "nana canvas print",
        ],
        "long_tail": [
            "personalized grandma gift with grandchildren names",
            "custom nana print with all grandkids names",
            "heartfelt grandmother birthday gift wall art",
            "nana christmas gift from grandkids print",
            "grandmother mothers day wall art personalized",
        ],
        "buyer_intent": [
            "best grandma gift ideas from grandkids",
            "personalized gifts for grandma",
            "unique grandmother birthday gift ideas",
        ],
    },
    "Grandpa Gift": {
        "high_volume": [
            "grandpa gift",
            "papa gift",
            "gift for grandpa",
            "grandfather wall art",
            "grandpa print",
        ],
        "mid_volume": [
            "personalized grandpa gift",
            "papa wall art",
            "grandpa birthday gift",
            "grandfather decor",
            "pops gift",
        ],
        "long_tail": [
            "personalized grandpa gift with grandchildren names",
            "custom papa print with all grandkids names",
            "heartfelt grandfather birthday gift wall art",
            "grandpa fishing cabin decor art print",
            "grandfather fathers day wall art personalized",
        ],
        "buyer_intent": [
            "best grandpa gift ideas from grandkids",
            "personalized gifts for grandpa",
            "unique grandfather birthday gift ideas",
        ],
    },
    "Best Friend Gift": {
        "high_volume": [
            "best friend gift",
            "bff gift",
            "friendship wall art",
            "bestie gift",
            "friend print",
        ],
        "mid_volume": [
            "soul sister gift",
            "long distance friend gift",
            "bff birthday gift",
            "friendship canvas",
            "galentines gift",
        ],
        "long_tail": [
            "personalized best friend birthday gift wall art",
            "long distance best friend moving away gift print",
            "soul sister friendship quote canvas print",
            "galentines day squad goals gift poster",
            "bff missing you long distance print",
        ],
        "buyer_intent": [
            "best friend birthday gift ideas",
            "meaningful friendship wall art",
            "unique bff gift ideas",
        ],
    },
    "Christian Wall Art": {
        "high_volume": [
            "christian wall art",
            "bible verse art",
            "scripture print",
            "faith wall art",
            "christian decor",
        ],
        "mid_volume": [
            "bible quote print",
            "faith home decor",
            "prayer wall art",
            "cross wall art",
            "scripture canvas",
        ],
        "long_tail": [
            "jeremiah 29 11 wall art print faith",
            "be still and know psalm 46 10 canvas",
            "she is clothed in strength proverbs 31 print",
            "trust in the lord proverbs 3 5 canvas",
            "christian home decor bible verse scripture poster",
        ],
        "buyer_intent": [
            "meaningful christian home decor gifts",
            "faith-based wall art for christian home",
            "bible verse print for christian house",
        ],
    },
    "Graduation Gift": {
        "high_volume": [
            "graduation gift",
            "grad wall art",
            "class of 2025",
            "graduate print",
            "graduation decor",
        ],
        "mid_volume": [
            "personalized graduation gift",
            "senior gift",
            "grad canvas",
            "diploma gift",
            "graduate keepsake",
        ],
        "long_tail": [
            "personalized graduation gift class of 2025 wall art",
            "dental school graduation gift dmd dds print",
            "medical school graduation MD graduate framed art",
            "nursing school graduation RN graduate print",
            "law school graduation JD graduate wall art",
        ],
        "buyer_intent": [
            "unique graduation gift ideas 2025",
            "meaningful personalized graduation gifts",
            "professional school graduation gift ideas",
        ],
    },
    "Memorial Gift": {
        "high_volume": [
            "memorial gift",
            "sympathy gift",
            "in memory of print",
            "memorial wall art",
            "grief gift",
        ],
        "mid_volume": [
            "condolence gift",
            "bereavement gift",
            "remembrance print",
            "loss of loved one",
            "memorial keepsake",
        ],
        "long_tail": [
            "in loving memory wall art personalized sympathy",
            "grief healing print comfort gift for loss",
            "memorial print for loss of father wall art",
            "sympathy gift loss of loved one art",
            "remembrance art for bereavement comfort",
        ],
        "buyer_intent": [
            "meaningful sympathy gift ideas",
            "thoughtful memorial gifts for grieving",
            "personalized in memory of wall art",
        ],
    },
    "Pet Memorial": {
        "high_volume": [
            "pet memorial",
            "dog memorial",
            "pet loss gift",
            "cat memorial",
            "rainbow bridge",
        ],
        "mid_volume": [
            "pet sympathy gift",
            "dog loss art",
            "cat loss print",
            "pet tribute",
            "golden retriever memorial",
        ],
        "long_tail": [
            "personalized dog memorial wall art with name",
            "cat memorial rainbow bridge comfort print",
            "golden retriever memorial canvas print gift",
            "pet loss sympathy gift in memory of dog",
            "beloved dog tribute framed wall art",
        ],
        "buyer_intent": [
            "meaningful pet memorial gift ideas",
            "dog loss sympathy gift ideas",
            "personalized pet memorial wall art",
        ],
    },
    "Future Dentist": {
        "high_volume": [
            "future dentist print",
            "dental student gift",
            "pre-dental gift",
            "DAT motivation",
            "dental school art",
        ],
        "mid_volume": [
            "aspiring dentist print",
            "dental student decor",
            "future DDS print",
            "DAT prep art",
            "dental motivation",
        ],
        "long_tail": [
            "future dentist motivational wall art for dental student",
            "pre-dental DAT motivation print for student",
            "dental school study motivation poster",
            "aspiring dentist gift from parent",
            "future DDS motivation art dental school",
        ],
        "buyer_intent": [
            "dental student gift ideas",
            "pre-dental motivation gift",
            "gift for aspiring dentist",
        ],
    },
    "Future Doctor": {
        "high_volume": [
            "future doctor print",
            "pre-med gift",
            "medical student gift",
            "MCAT motivation",
            "future MD art",
        ],
        "mid_volume": [
            "aspiring doctor print",
            "pre-med decor",
            "medical student art",
            "doctor motivation",
            "future physician",
        ],
        "long_tail": [
            "future doctor motivational wall art for pre-med student",
            "MCAT motivation print for medical student",
            "medical school study motivation poster",
            "aspiring doctor gift from parent",
            "future MD motivation art medical school",
        ],
        "buyer_intent": [
            "pre-med student gift ideas",
            "medical student motivation gift",
            "gift for aspiring doctor",
        ],
    },
    "Future Nurse": {
        "high_volume": [
            "future nurse print",
            "nursing student gift",
            "NCLEX motivation",
            "nursing school art",
            "future RN",
        ],
        "mid_volume": [
            "aspiring nurse print",
            "nursing student decor",
            "nurse motivation",
            "student nurse art",
            "nursing motivation",
        ],
        "long_tail": [
            "future nurse motivational wall art for nursing student",
            "NCLEX motivation print for nursing student",
            "nursing school study motivation poster",
            "aspiring nurse gift from parent",
            "future RN motivation art nursing school",
        ],
        "buyer_intent": [
            "nursing student gift ideas",
            "nurse student motivation gift",
            "gift for aspiring nurse",
        ],
    },
    "Dental School": {
        "high_volume": [
            "dental school gift",
            "DMD graduate",
            "DDS graduate",
            "dental graduation",
            "dentist gift",
        ],
        "mid_volume": [
            "dental boards motivation",
            "white coat ceremony",
            "dental practice decor",
            "new dentist gift",
            "dental office art",
        ],
        "long_tail": [
            "dental school graduation gift DMD DDS print",
            "DAT motivation print for pre-dental student",
            "INBDE NBDE board exam motivation poster",
            "white coat ceremony dental school gift",
            "new dental practice owner opening day print",
        ],
        "buyer_intent": [
            "dental school graduation gift ideas",
            "dental student gift ideas",
            "dentist office decor ideas",
        ],
    },
    "Healthcare Worker": {
        "high_volume": [
            "healthcare worker gift",
            "nurse gift",
            "doctor gift",
            "medical worker art",
            "frontline gift",
        ],
        "mid_volume": [
            "healthcare decor",
            "medical professional",
            "hospital worker art",
            "clinical art",
            "caregiver gift",
        ],
        "long_tail": [
            "healthcare worker appreciation wall art print",
            "nurse doctor appreciation gift framed poster",
            "medical professional office decor print",
            "frontline worker motivation wall art",
            "caregiver appreciation art for hospital worker",
        ],
        "buyer_intent": [
            "healthcare worker appreciation gift ideas",
            "meaningful nurse gift ideas",
            "medical professional decor ideas",
        ],
    },
    "ICU Nurse": {
        "high_volume": [
            "ICU nurse gift",
            "critical care nurse",
            "ICU wall art",
            "intensive care gift",
            "ICU decor",
        ],
        "mid_volume": [
            "ICU nurse print",
            "critical care art",
            "hospital ICU",
            "ICU motivation",
            "critical nurse",
        ],
        "long_tail": [
            "ICU nurse appreciation wall art gift",
            "critical care nurse motivation print",
            "intensive care unit nurse framed art",
            "ICU nurse graduation gift print",
            "hospital critical care appreciation poster",
        ],
        "buyer_intent": [
            "ICU nurse gift ideas",
            "critical care nurse appreciation gifts",
            "gift ideas for intensive care nurse",
        ],
    },
    "Teacher Gift": {
        "high_volume": [
            "teacher gift",
            "gift for teacher",
            "teacher wall art",
            "teacher appreciation",
            "teacher decor",
        ],
        "mid_volume": [
            "teacher quote print",
            "classroom art",
            "educator gift",
            "teacher print",
            "school teacher",
        ],
        "long_tail": [
            "personalized teacher appreciation gift wall art",
            "teacher end of year gift print from student",
            "classroom motivational wall art for teacher",
            "christian teacher faith in education print",
            "elementary school teacher quote art poster",
        ],
        "buyer_intent": [
            "teacher appreciation gift ideas",
            "end of year teacher gift ideas",
            "meaningful gifts for teachers",
        ],
    },
    "Wedding Gift": {
        "high_volume": [
            "wedding gift",
            "couples wall art",
            "wedding decor",
            "bridal gift",
            "newlywed gift",
        ],
        "mid_volume": [
            "personalized wedding gift",
            "mr and mrs art",
            "wedding print",
            "couple art",
            "bride groom art",
        ],
        "long_tail": [
            "personalized wedding gift couples wall art print",
            "custom wedding vows framed art print",
            "mr and mrs first home newlywed wall art",
            "bridal shower gift personalized print",
            "love story how we met couples art",
        ],
        "buyer_intent": [
            "unique wedding gift ideas",
            "personalized wedding gifts for couple",
            "meaningful bridal shower gift ideas",
        ],
    },
    "Anniversary Gift": {
        "high_volume": [
            "anniversary gift",
            "anniversary wall art",
            "couples anniversary",
            "wedding anniversary",
            "milestone anniversary",
        ],
        "mid_volume": [
            "personalized anniversary",
            "anniversary print",
            "silver anniversary",
            "golden anniversary",
            "anniversary canvas",
        ],
        "long_tail": [
            "personalized anniversary gift wall art for couple",
            "25th silver anniversary framed art print",
            "50th golden anniversary canvas gift",
            "1st paper anniversary couples print",
            "10th tin anniversary milestone art",
        ],
        "buyer_intent": [
            "unique anniversary gift ideas for couple",
            "personalized anniversary gifts",
            "meaningful milestone anniversary gifts",
        ],
    },
    "Baby Shower": {
        "high_volume": [
            "baby shower gift",
            "nursery wall art",
            "new baby print",
            "baby name art",
            "birth stats print",
        ],
        "mid_volume": [
            "personalized baby shower",
            "nursery decor",
            "birth announcement",
            "baby birth art",
            "newborn print",
        ],
        "long_tail": [
            "personalized baby shower gift birth stats wall art",
            "custom baby name nursery print for newborn",
            "birth announcement art with name date weight",
            "nursery wall art personalized baby gift",
            "new baby custom stats poster for nursery",
        ],
        "buyer_intent": [
            "unique baby shower gift ideas",
            "personalized baby gifts",
            "meaningful nursery decor gifts",
        ],
    },
    "New Mom Gift": {
        "high_volume": [
            "new mom gift",
            "first time mom",
            "motherhood wall art",
            "baby shower mom",
            "mama gift",
        ],
        "mid_volume": [
            "new mother print",
            "first mothers day",
            "new mama decor",
            "mama art",
            "motherhood print",
        ],
        "long_tail": [
            "first time mom gift motherhood wall art print",
            "new mama encouragement poster gift",
            "first mothers day gift for new mom",
            "baby shower gift for new mother wall art",
            "motherhood journey art print for new mom",
        ],
        "buyer_intent": [
            "new mom gift ideas",
            "first mothers day gift ideas",
            "meaningful gifts for new mothers",
        ],
    },
    "Mental Health Art": {
        "high_volume": [
            "mental health art",
            "anxiety healing print",
            "self love wall art",
            "healing decor",
            "affirmation art",
        ],
        "mid_volume": [
            "self worth print",
            "recovery art",
            "grief healing",
            "sobriety gift",
            "positive affirmation",
        ],
        "long_tail": [
            "mental health healing wall art anxiety comfort print",
            "self love affirmation bedroom wall art poster",
            "sobriety recovery motivation gift wall art",
            "grief healing comfort print sympathy art",
            "you are enough positive affirmation bedroom decor",
        ],
        "buyer_intent": [
            "mental health art gift ideas",
            "healing wall art for anxiety",
            "meaningful self-love gift ideas",
        ],
    },
    "Fitness Gym Decor": {
        "high_volume": [
            "gym wall art",
            "fitness decor",
            "workout motivation",
            "home gym art",
            "gym poster",
        ],
        "mid_volume": [
            "runner gift",
            "yoga decor",
            "bodybuilding art",
            "marathon gift",
            "gym canvas",
        ],
        "long_tail": [
            "home gym motivation wall art fitness poster",
            "marathon runner gift wall art print",
            "yoga studio meditation wall art decor",
            "bodybuilding powerlifting gym canvas",
            "workout motivation poster for home gym",
        ],
        "buyer_intent": [
            "home gym decor gift ideas",
            "workout motivation art ideas",
            "gym wall art for fitness lovers",
        ],
    },
    "Office Motivation": {
        "high_volume": [
            "office wall art",
            "motivation print",
            "leadership art",
            "workplace decor",
            "entrepreneur art",
        ],
        "mid_volume": [
            "boss office art",
            "team motivation",
            "business print",
            "hustle art",
            "work life balance",
        ],
        "long_tail": [
            "office motivational wall art leadership print",
            "entrepreneur business motivation art poster",
            "work life balance office wellness print",
            "teamwork office motivation wall art poster",
            "CEO founder office inspirational canvas",
        ],
        "buyer_intent": [
            "office motivation art gift ideas",
            "leadership wall art for office",
            "meaningful entrepreneur gift ideas",
        ],
    },
    "Mountain Wall Art": {
        "high_volume": [
            "mountain wall art",
            "mountain print",
            "mountain decor",
            "scenic wall art",
            "nature print",
        ],
        "mid_volume": [
            "mountain poster",
            "adventure art",
            "hiking decor",
            "mountain canvas",
            "outdoor art",
        ],
        "long_tail": [
            "mountain wall art print for living room decor",
            "scenic mountain print adventure home decor",
            "custom mountain print personalized quote art",
            "mountain nature art for cabin lodge decor",
            "inspirational mountain quote poster print",
        ],
        "buyer_intent": [
            "mountain wall art gift ideas",
            "scenic nature decor for home",
            "mountain art for outdoor lovers",
        ],
    },
    "Beach Wall Art": {
        "high_volume": [
            "beach wall art",
            "beach print",
            "ocean decor",
            "coastal art",
            "beach decor",
        ],
        "mid_volume": [
            "beach poster",
            "ocean print",
            "coastal decor",
            "beach canvas",
            "nautical art",
        ],
        "long_tail": [
            "beach wall art print for coastal home decor",
            "ocean wave print beach house wall art",
            "coastal living room art personalized quote",
            "beach vacation home art nautical decor",
            "lake house beach art personalized print",
        ],
        "buyer_intent": [
            "beach wall art gift ideas",
            "coastal home decor art ideas",
            "beach house wall art",
        ],
    },
    "Faith Wall Art": {
        "high_volume": [
            "faith wall art",
            "christian art",
            "bible verse print",
            "scripture decor",
            "faith decor",
        ],
        "mid_volume": [
            "faith canvas",
            "prayer art",
            "worship decor",
            "scripture art",
            "faith poster",
        ],
        "long_tail": [
            "faith wall art for christian home decor",
            "bible verse print personalized scripture art",
            "prayer wall art faith home canvas",
            "christian home decor faith quote poster",
            "scripture verse art for church or home",
        ],
        "buyer_intent": [
            "faith wall art gift ideas",
            "christian home decor gift ideas",
            "meaningful bible verse art gifts",
        ],
    },
}


def search_keywords(query: str) -> dict[str, list[str]]:
    """Search keyword DB for a niche matching the query."""
    query_lower = query.lower()
    return {
        niche: kws
        for niche, kws in KEYWORD_DB.items()
        if query_lower in niche.lower()
    }


def get_best_tags_for_niche(niche: str, count: int = 13) -> list[str]:
    """Return the best Etsy tags for a niche (high_volume first, then mid)."""
    data = KEYWORD_DB.get(niche, {})
    pool = data.get("high_volume", []) + data.get("mid_volume", [])
    # Etsy tags max 20 chars each
    tags = [t for t in pool if len(t) <= 20]
    return tags[:count]
