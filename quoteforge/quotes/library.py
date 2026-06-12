"""Curated original quote library, organized by occasion category."""
import random

QUOTE_LIBRARY: dict[str, list[str]] = {
    "Faith & Spiritual": [
        # Christian encouragement
        "Let your faith be bigger than your fear.",
        "Faith over fear — always.",
        "God is within her. She will not fall.",
        "Be still and know that you are held.",
        "Every morning is a reminder that grace is new.",
        "God's timing is always perfect.",
        "Let go and let grace guide you.",
        "The light within you is stronger than any darkness around you.",
        "Trust the journey even when you cannot see the road.",
        "Blessed are those who believe before they see.",
        "Walk by faith, not by sight.",
        # Bible verse inspired (paraphrased originals — not direct quotes)
        "I can do all things through the strength I have been given.",
        "For I know the plans for you — plans for hope and a future.",
        "Be strong and courageous. Do not be afraid.",
        "Trust in the Lord with all your heart and lean not on your own understanding.",
        "I will never leave you nor forsake you.",
        # Prayer & hope
        "In every storm, peace waits in the shelter of prayer.",
        "Grace is not earned — it is freely given.",
        "Where hope grows, miracles blossom.",
        "Prayer is not asking — it is listening.",
        # Baptism / confirmation / sacraments
        "A new life washed in grace and love.",
        "Confirmed in faith, rooted in love.",
        "Today you begin your walk with purpose and grace.",
        "Received into the family of faith — welcome.",
        # Easter
        "He is risen — and because of that, everything is different.",
        "Because of Easter, hope has the final word.",
        "Death could not hold what love had claimed.",
        # Christmas nativity
        "Peace on earth begins in the heart.",
        "A savior was born and love came down.",
        "The greatest gift was wrapped not in paper, but in grace.",
        # General spiritual
        "The universe bends toward those who trust it.",
        "You were made for more than you can imagine.",
        "Gratitude turns what you have into enough.",
    ],

    "Healing & Wellness": [
        # Mental health
        "Healing is not linear — every step forward counts.",
        "You are allowed to take up space in this world.",
        "Rest is not giving up — it is gathering strength.",
        "Your feelings are valid. Your recovery is real.",
        "Be patient with yourself — growth takes time.",
        "You survived every hard day so far. Today is no different.",
        "Peace is not the absence of pain. It is choosing yourself anyway.",
        "Every breath is a new beginning.",
        "You are worthy of kindness, especially from yourself.",
        "Healing happens slowly, then all at once.",
        # Progress not perfection
        "Progress, not perfection.",
        "You do not have to be perfect. You just have to keep going.",
        "Small steps every day still move you forward.",
        "Done is better than perfect. Begin.",
        # One day at a time
        "One day at a time. One breath at a time.",
        "You do not have to figure out forever today. Just today.",
        "Today is enough. You are enough.",
        # Trust the process
        "Trust the process even when the process is hard.",
        "Growth takes time. Roots before branches.",
        "What is growing in you right now cannot be rushed.",
        # Choose joy
        "Choose joy — not because life is easy, but because you are strong.",
        "Joy is not found. It is chosen.",
        "Choose peace daily.",
        # You can do hard things
        "You can do hard things.",
        "You have already survived your hardest days. Keep going.",
        "Keep going. You are closer than you think.",
    ],

    "Love & Relationships": [
        # Anniversary / wedding
        "Love is not a destination — it is the journey taken together.",
        "In your arms, I found my home.",
        "The best thing to hold onto in life is each other.",
        "A great love is not found — it is built, day by day.",
        "Still my favorite person after all this time.",
        "Still choosing you. Every single day.",
        "Together is my favorite place to be.",
        "Forever starts today.",
        "Love grows best in small houses and big hearts.",
        "You are my today and all of my tomorrows.",
        "Growing together, always.",
        # Motherhood
        "A mother's love is the compass that guides us home.",
        "Mom, thank you for everything.",
        "A mother is a forever kind of love.",
        "The love of a mother is the heart of a family.",
        # Fatherhood
        "A father's love is the quiet strength that shapes a child's world.",
        "Behind every great child is a dad who believed first.",
        "A dad is someone who lifts you up even when life weighs him down.",
        # Grandparents
        "A grandmother's love is a treasure that never fades.",
        "Grandpa: the man who makes everything feel right.",
        "Some people make the world more beautiful just by being in it — grandma.",
        # Children
        "A daughter is a blessing wrapped in grace.",
        "A son is a forever piece of your heart.",
        "Children are the living messages we send to a time we will not see.",
        # Siblings / friends
        "A sister is a forever friend.",
        "Brothers: born together, friends forever.",
        "True friendship doubles joy and divides grief.",
        "Best friends are the family we choose.",
        # Family
        "Family: where life begins and love never ends.",
        "Home is not a place — it is the people in it.",
    ],

    "Life Events": [
        # Graduation
        "The best is yet to come.",
        "Dream big. Start now.",
        "Your journey starts here.",
        "You did not just earn a degree — you earned your story.",
        "Go forth and be remarkable.",
        "Today is the first page of a brand new chapter.",
        # New job / promotion
        "Success is earned daily.",
        "Keep climbing. The view gets better.",
        "Promoted: because excellence speaks for itself.",
        "Every expert was once a beginner who refused to quit.",
        "You worked for this. Now own it.",
        # Retirement
        "The adventure begins.",
        "Enjoy the journey — you have earned every step.",
        "Retirement: not the end of work, but the beginning of freedom.",
        "Now the real fun begins.",
        "You gave your best years. Now live your best life.",
        # New home / housewarming
        "Home is where your story begins.",
        "Bless this home.",
        "New home, new memories, new story.",
        "May this home be filled with laughter, love, and peace.",
        "Every great story needs a great home.",
        # Wedding
        "Together is my favorite place to be.",
        "Forever starts today.",
        "Two lives, one love story.",
        "Today I choose you. Tomorrow I choose you again.",
        # Baby shower / new parents
        "Welcome, little one.",
        "Adventure awaits, little one.",
        "You are loved beyond measure.",
        "The world just got a little brighter — welcome.",
        "Tiny hands, enormous love.",
        "The greatest chapter begins with a tiny heartbeat.",
        # New beginnings
        "A new beginning is the bravest kind of chapter.",
        "You did not come this far only to come this far.",
        "Every ending is a new beginning in disguise.",
        "Look how far you have come — and look how far you will go.",
    ],

    "Motivation & Mindset": [
        "The difference between ordinary and extraordinary is that little extra.",
        "Start before you are ready. Grow as you go.",
        "Discipline is choosing what you want most over what you want now.",
        "Success is not given. It is built one decision at a time.",
        "Your only competition is who you were yesterday.",
        "Dream big. Work hard. Stay humble.",
        "The grind is silent. The results are loud.",
        "Every expert was once a beginner who refused to quit.",
        "Create the life you cannot stop thinking about.",
        "Hard work beats talent when talent does not work hard.",
        "Great leaders do not create followers — they create more leaders.",
        "Innovation begins where comfort ends.",
        "Keep going. You are closer than you think.",
        "Discipline beats motivation every single time.",
        "Make this year count.",
        "Do something today your future self will thank you for.",
        "The only bad workout is the one that did not happen.",
        "Rise up and attack the day with enthusiasm.",
        "Stronger every day.",
        "Train with purpose. Live with intention.",
    ],

    "Professional Niches": [
        # Nurse / healthcare
        "Nurses: the heart of healthcare.",
        "Changing lives one patient at a time.",
        "Compassion is the foundation of healing.",
        "She chose nursing because the world needed more heroes.",
        "Not all angels have wings — some wear scrubs.",
        "Nurses do not just care for patients. They carry them.",
        # Doctor
        "Medicine is the art of keeping hope alive.",
        "Heal with skill. Lead with compassion.",
        "A great doctor listens before they speak.",
        # Dental
        "Changing lives one smile at a time.",
        "A great smile starts with great care.",
        "The best tool a dentist has is a genuine heart.",
        # Teacher
        "Teachers plant seeds that grow forever.",
        "A great teacher creates more than lessons — they create futures.",
        "Teaching is the one profession that creates all others.",
        "You may forget what a teacher said, but never how they made you feel.",
        "One great teacher can change everything.",
        # Engineer
        "Build something the world will remember.",
        "Engineers do not just build things — they build the future.",
        # Police / firefighter
        "Courage is not the absence of fear. It is running toward it anyway.",
        "Police officers: standing between order and chaos every day.",
        "The firefighter runs toward the fire so you do not have to.",
        # Military
        "Honor the fallen by living with purpose.",
        "Service before self. Every single day.",
        "Freedom is not free — it is protected by the brave.",
        # Veterinarian
        "They cannot speak for themselves. You speak for them.",
        "Caring for those who give us unconditional love.",
    ],

    "Fitness & Sports": [
        "Stronger every day.",
        "Train with purpose.",
        "Discipline beats motivation.",
        "Your only limit is the one you set.",
        "One more rep. One more mile. One more reason.",
        "The body achieves what the mind believes.",
        "Sweat is just your fat crying.",
        "Push yourself because no one else will do it for you.",
        "Fall in love with the process and the results will follow.",
        "Champions are made in the moments they want to quit.",
        "Run the day. Do not let the day run you.",
        "Yoga is not about touching your toes. It is about what you learn on the way down.",
        "Find your strength. Own your story.",
        "Every rep is a vote for the person you are becoming.",
        "Hard work pays off — always.",
        "Be stronger than your excuses.",
    ],

    "Holidays & Seasonal": [
        # New Year
        "New year, new beginnings.",
        "Make this year count.",
        "New year, same soul — but braver and wiser.",
        "Every new year is a blank page. Write something beautiful.",
        # Valentine's Day
        "Love never fails.",
        "You are my home.",
        "Love is not just for today — it is for every day.",
        "You are the reason I believe in love.",
        # St. Patrick's Day
        "May your luck be as endless as the Irish hills.",
        "Lucky to have you.",
        # Easter
        "He is risen — and because of that, everything is different.",
        "Because of Easter, hope has the final word.",
        # Mother's Day
        "To the woman who made home feel like heaven — Happy Mother's Day.",
        "Mom: my first friend, my forever hero.",
        "The world is better because you are a mother in it.",
        # Father's Day
        "Behind every great child is a dad who believed first.",
        "Dad: the man who holds everything together.",
        # Memorial Day
        "Honor the fallen by living with purpose.",
        "Freedom is never free. Remember those who paid the price.",
        # Independence Day
        "Land of the free because of the brave.",
        "Born free. Live free.",
        # Labor Day
        "Hard work is never wasted.",
        "The dignity of labor is the foundation of a great life.",
        # Halloween
        "Be the kind of person who brings the candy.",
        "Spooky season — the time of year when magic feels real.",
        # Thanksgiving
        "Grateful hearts make grateful homes.",
        "Gratitude turns what you have into enough.",
        "There is always something to be thankful for.",
        # Christmas
        "May your Christmas be wrapped in peace and tied with love.",
        "Peace on earth begins in the heart.",
        "The greatest gift is the people around the table.",
        # Hanukkah
        "Eight nights of light, love, and miracles.",
        "The light that pushed back the darkness — still shining.",
        # New Year's Eve
        "Cheers to new chapters and brave beginnings.",
        "Tonight we celebrate. Tomorrow we rise.",
    ],

    "Seasonal Collections": [
        # Spring
        "Spring: proof that after every winter, life begins again.",
        "Bloom where you are planted.",
        "Every spring is a reminder that growth follows rest.",
        "The earth laughs in flowers.",
        "Spring growth collection: new season, new you.",
        # Summer
        "Summer is the season when memories are made and kept forever.",
        "Chase sunsets. Collect moments.",
        "Life is better with sand between your toes.",
        "Good vibes and sunshine.",
        # Autumn
        "Fall: the art of letting go beautifully.",
        "Autumn leaves and gratitude.",
        "There is beauty in letting go.",
        "Every leaf is a flower before it falls.",
        "Cozy season. Grateful heart.",
        # Winter
        "Winter is not the end — it is the earth resting before it blooms.",
        "Winter peace collection.",
        "In the stillness of winter, something beautiful is preparing to grow.",
        "Let it snow. Let it go.",
        "Warmth is not a season — it is a choice.",
    ],

    "Civic & Political": [
        "Freedom is not free — it is purchased with courage and sacrifice.",
        "Democracy is not a spectator sport. Vote.",
        "We do not inherit the earth from our ancestors — we borrow it from our children.",
        "Honor the fallen by living with purpose.",
        "Service to others is the rent we pay for our place on earth.",
        "In unity there is strength. In strength there is freedom.",
        "The firefighter runs toward the fire so you do not have to.",
        "A nation's character is measured by how it treats its most vulnerable.",
        "Your voice matters. Your vote matters. Show up.",
        "Heroes are ordinary people who make extraordinary choices.",
        "Born free. Live free. Give freely.",
        "One nation, under hope.",
    ],

    "Nature & Scenic": [
        # Mountains
        "The mountains teach us that the higher you climb, the better the view.",
        "Not all who wander are lost — some are just finding themselves.",
        "Rise above the clouds. The summit awaits.",
        "In the mountains, I find my peace.",
        # Beach / ocean
        "In the waves of change, I found my direction.",
        "The ocean does not apologize for its depth. Neither should you.",
        "Life is better at the beach.",
        "Let the waves wash away what no longer serves you.",
        "Salt air. Bare feet. Free spirit.",
        # Forest
        "The forest is the original cathedral.",
        "Go where the trees are tall and the noise is quiet.",
        "In the woods, I find what the city takes away.",
        # Sunrise / sunset
        "Be still and let the morning remind you — today is a gift.",
        "Every sunset carries the seeds of tomorrow's sunrise.",
        "Chase sunrises. They remind you that new beginnings are daily.",
        # Stars / night
        "Stars remind us that even in darkness, light exists.",
        "Look up. The universe is larger than your worry.",
        # Waterfalls
        "Like a waterfall — keep moving and you will create something beautiful.",
        "Flow. Do not force.",
        # Wildflowers
        "Wildflowers do not ask permission to bloom. Neither should you.",
        "Bloom in your own season.",
        # General nature / peace
        "Slow down. The earth has been here longer than your hurry.",
        "Peace begins where nature begins.",
        "Nature does not rush — yet everything gets done.",
    ],

    "Room Decor": [
        # Office / workspace
        "Do what you love and the work will show it.",
        "This is where the magic happens.",
        "Dream. Plan. Execute.",
        "Create. Inspire. Repeat.",
        # Home
        "Home: where every story worth telling begins.",
        "Bless this house with love and laughter.",
        "The best memories are made right here.",
        # Bedroom
        "Rest. Restore. Rise.",
        "Dream big, even while you sleep.",
        "Tomorrow needs a rested version of you.",
        # Nursery
        "You are loved beyond measure, little one.",
        "Dream big, tiny dreamer.",
        "Welcome to the world, little miracle.",
        # Dorm room
        "You did not come this far to only come this far.",
        "This is where your future begins.",
        "Study hard. Dream big. Rise higher.",
        # Classroom
        "This classroom runs on curiosity and courage.",
        "Every great thinker started right where you are.",
        "Learn. Grow. Lead.",
        # Gym
        "Train hard. Live well.",
        "This is where excuses come to die.",
        "Stronger every single day.",
    ],

    "Office & Business": [
        "Great teams do not happen by accident — they are built with intention.",
        "Do what you love and you will never work a day in your life.",
        "Success is a team sport. Nobody wins alone.",
        "Ideas without action are just dreams. Act.",
        "Work hard in silence. Let success make the noise.",
        "Balance is not something you find — it is something you build.",
        "Create. Innovate. Lead.",
        "Your work is a reflection of your standards. Set them high.",
        "Leaders do not wait for permission to lead.",
        "Build something you are proud of.",
        "The best investment you can make is in yourself.",
        "Culture eats strategy for breakfast. Build the culture first.",
        "Five posters. One vision. Unstoppable team.",
    ],

    "Dental School & Healthcare": [
        # DAT / pre-dental
        "The DAT is one door. Dentistry is a whole world.",
        "Every practice question is one step closer to Doctor of Dental Surgery.",
        "Pre-dental today. Changing smiles forever.",
        "Study like the patients are already waiting.",
        "The grind today is the degree tomorrow.",
        # Dental school journey
        "Dental school is not just education — it is transformation.",
        "You chose one of the hardest paths because you are built for it.",
        "Boards are a season. Your career is a lifetime.",
        "Anatomy is not just a class — it is the foundation of every life you will save.",
        "Two years of science. Two years of clinic. A lifetime of purpose.",
        # Future DDS / white coat
        "One day you will wear the white coat and wonder how you ever doubted yourself.",
        "Future DDS: the credential is coming. The calling is already here.",
        "The white coat is not just fabric — it is the weight of trust and the gift of healing.",
        "Doctor of Dental Surgery: earned in exhaustion, worn in pride.",
        # Practice owner
        "One day your name will be on the door. Keep going.",
        "Your future patients are waiting for the dentist only you can be.",
        "Dream of the practice. Build the skills. Open the door.",
        # Dental hygienist
        "Changing lives one smile at a time.",
        "Dental hygienists: the quiet heroes of preventive care.",
        "Every cleaned tooth is a small act of love.",
    ],

    "Future Professions": [
        "Future Dentist: the chair is waiting.",
        "Future Doctor: the patients need who you are becoming.",
        "Future Nurse: compassion is already in you.",
        "Future Teacher: the classroom needs your gift.",
        "Future Engineer: build the world no one else can imagine.",
        "Future Lawyer: justice needs your voice.",
        "Future Veterinarian: the animals trust you before you even begin.",
        "Future Entrepreneur: the idea that keeps you up at night is the one that matters.",
        "Not yet arrived — but already becoming.",
        "The degree comes later. The calling is now.",
        "Vision boards are just the beginning. Execution is everything.",
        "Affirm it. Believe it. Become it.",
        "Every great professional once sat exactly where you are sitting.",
    ],

    "Children's Confidence": [
        "Brave little dreamer.",
        "You can learn anything.",
        "You are braver than you know.",
        "Be kind. Be curious. Be you.",
        "You were made to shine.",
        "You are enough, just as you are.",
        "Dream big, little one.",
        "Your ideas matter. Your voice matters. You matter.",
        "You can do hard things — even the hard things.",
        "Kindness is always the right answer.",
        "The world is better because you are in it.",
        "You are smart. You are loved. You are capable.",
        "Be yourself — everyone else is taken.",
        "Grow at your own pace. Bloom in your own season.",
        "You are a miracle in motion.",
    ],

    "Recovery & Healing Journey": [
        # Divorce / new chapter
        "What feels like an ending is also a beginning.",
        "Starting over is an act of tremendous courage.",
        "You are not starting from scratch. You are starting from experience.",
        "The chapter closed. The story continues.",
        # Grief & loss
        "Grief is love with nowhere to go — let it move through you.",
        "You do not have to be strong every day. Just today.",
        "Missing them is not weakness. It is love that has no expiration date.",
        # Addiction recovery
        "One day at a time. One hour at a time. One breath at a time.",
        "Recovery is not giving something up. It is getting your life back.",
        "Sobriety is not a destination. It is a daily choice you keep winning.",
        # Cancer / illness
        "Healing is not linear — but you are always moving forward.",
        "Survivor: a title worn with scars and grace.",
        "The body heals. The spirit endures. The story continues.",
        # General healing
        "You are allowed to grieve, to rest, and to rise again.",
        "There is no timeline for healing. Just keep moving.",
        "What broke you open also let the light in.",
        "You are still here. That matters more than you know.",
    ],

    "Personalized — Life Chapters": [
        # These are template starters — Claude generates the personalized versions
        "Chapter [Age]: Becoming Who You Were Always Meant To Be.",
        "This is the chapter where everything changes.",
        "The hard chapters are the ones worth writing.",
        "You did not come this far to only come this far.",
        "Every chapter has prepared you for this one.",
        "The best chapters are the ones no one saw coming.",
        "Your story is still being written. Keep going.",
    ],

    "Personalized — Family Legacy": [
        # Template starters — Claude fills in the family name
        "Where faith meets family, legacy is built.",
        "Built on love. Rooted in purpose. Growing still.",
        "A name is not just what you are called — it is what you stand for.",
        "The greatest inheritance is the values we pass on.",
        "Family: the first community, the lasting legacy.",
        "Every generation adds a new chapter to the family story.",
        "Home is where the legacy begins.",
    ],

    "Airport & Aviation": [
        "Not all who wander are lost — some have a boarding pass.",
        "The sky is not the limit. It is home.",
        "Born to fly. Trained to land safely.",
        "Pilots do not just fly planes — they carry dreams.",
        "Cleared for takeoff. Cleared for greatness.",
        "Flight attendants: grace under pressure at 35,000 feet.",
        "Air traffic control: the unseen hands that keep the sky safe.",
        "Every great journey begins with a boarding pass and a leap of faith.",
        "Fly high. Land well. Go again.",
        "The runway is just the beginning.",
    ],
    "National Parks": [
        "In every walk with nature, one receives far more than they seek.",
        "The wilderness holds answers to questions we have not yet learned to ask.",
        "Leave it better than you found it.",
        "National parks: the best idea America ever had.",
        "Some places are so beautiful they make you believe in something greater.",
        "The mountains are calling. The parks are waiting.",
        "Protect wild places — they protect your soul.",
        "Yellowstone: where the earth still breathes.",
        "Grand Canyon: carved by time, filled with wonder.",
        "Great Smoky Mountains: where every season is a masterpiece.",
        "Yosemite: where granite meets grace.",
        "Zion: carved by faith and water.",
        "Leave only footprints. Take only memories.",
    ],
    "State Pride": [
        "Georgia: where peaches are sweet and roots run deep.",
        "Florida: sunshine, salt air, and soul.",
        "Texas: big land, bigger heart, biggest pride.",
        "Tennessee: where the mountains meet the music.",
        "California: dream it, live it, love it.",
        "North Carolina: mountains to the sea, beauty in between.",
        "Colorado: elevation of land and spirit.",
        "Born and raised here. Proud every day.",
        "Home is not just a place — it is a state of being.",
        "Some people are lucky enough to call this place home.",
        "This land shaped me. I carry it everywhere.",
    ],
    "Pet Lovers": [
        # Dog memorial
        "Not gone, just waiting at the rainbow bridge.",
        "A dog's love is the closest thing to unconditional grace.",
        "You were only here for a season, but you changed me forever.",
        "Good dogs never really leave — they live in the love they gave.",
        # Cat memorial
        "Cats do not just live in our homes — they live in our hearts.",
        "You purred your way into my soul and never left.",
        # Breed-specific
        "Golden Retrievers: love in fur form.",
        "German Shepherds: loyal beyond measure, brave beyond words.",
        "Labradors: proof that a good heart can wear a wagging tail.",
        # General pet love
        "My dog taught me more about unconditional love than any book ever could.",
        "The best therapist I ever had had four paws.",
        "A house is not a home without pet hair on everything.",
        "Pets fill a corner of your heart no human ever could.",
    ],
    "Indian & South Asian": [
        # Malayalam / Kerala
        "Kerala: where the backwaters carry the stories of generations.",
        "In the land of coconut palms and monsoon grace, roots run deep.",
        "Malayalam: a language that sounds like music and tastes like home.",
        # Indian Christian
        "Faith grew here long before the world knew its name.",
        "Indian Christian heritage: where ancient faith meets enduring love.",
        "Blessed by grace. Rooted in heritage. Growing in faith.",
        # Traditional Indian proverbs (original paraphrases)
        "A home with an elder is a home with a library.",
        "The fruit of patience is always sweet.",
        "Where love dwells, no storm can uproot the family.",
        # Indian wedding / family
        "Two families. One love. A story that begins today.",
        "Indian weddings do not just join two people — they join two worlds.",
        "Family is the original blessing.",
        # Diwali
        "Let the light of Diwali remind us — darkness never wins.",
        "Diwali: the festival of lights, the victory of hope.",
    ],
    "Men's Market": [
        # Father-son
        "A father's greatest gift is the man his son becomes.",
        "Father and son: different chapters of the same great story.",
        "Dad, you taught me how to be a man before I knew I needed it.",
        # Hunting / fishing
        "The hunt is not about the trophy — it is about the silence and the patience.",
        "Fishing: the art of doing nothing that matters enormously.",
        "Early mornings, cold coffee, and the best kind of quiet.",
        "Hunting season: where memories are made and traditions are kept.",
        # Leadership / strength
        "A real man lifts others as he climbs.",
        "Strength is not just muscle — it is character under pressure.",
        "Men of honor do not chase respect. They earn it quietly.",
        # Veterans
        "Veteran: earned in service, worn with pride.",
        "He left as a soldier. He came back as a man who carries something most will never understand.",
        # Brotherhood / man cave
        "Brotherhood: built in the field, forged in fire, kept forever.",
        "This is my space. My rules. My peace.",
    ],
    "Wedding Industry": [
        "Two imperfect people choosing to be perfect for each other.",
        "Today I marry my best friend.",
        "Together is my favorite place to be.",
        "Forever starts right here.",
        "Welcome — you are exactly where love lives.",
        "She said yes. Everything changes now.",
        "Mr. & Mrs.: the beginning of our best chapter.",
        "Love brought us here. Grace will carry us forward.",
        "This is where two stories become one.",
        "With this ring, I choose you — today, tomorrow, always.",
        "Eat, drink, and be married.",
    ],
    "Financial Independence": [
        "Wealth is not about money — it is about options.",
        "Build assets while others build expenses.",
        "Financial freedom is not a dream. It is a decision.",
        "Invest in your future self — they will thank you.",
        "The best time to plant a money tree was yesterday. The second best time is now.",
        "Your net worth is your future freedom.",
        "FIRE: Financial Independence. Your rules. Your timeline.",
        "Spend less than you earn. Invest the difference. Repeat.",
        "Abundance is a mindset before it is a bank balance.",
        "Build wealth quietly. Live fully. Give generously.",
    ],
    "Faith-Based Professions": [
        # Christian nurse
        "I am a nurse because God needed hands that heal with both skill and love.",
        "Called to care. Equipped by grace. Sustained by faith.",
        "Christian nurse: where medicine meets ministry.",
        # Christian dentist
        "God called me to restore smiles. I show up every day to answer that call.",
        "Every patient in my chair is someone God loves — I treat them accordingly.",
        "Christian dentist: healing mouths, serving hearts.",
        # Christian teacher
        "I teach because every child is made in the image of the greatest Teacher.",
        "Called to the classroom. Faithful in the mission.",
        "Christian teacher: planting seeds of truth in every lesson.",
        # Christian athlete
        "I run for an audience of one.",
        "Train the body. Strengthen the faith. Compete with grace.",
        "Christian athlete: the victory that matters most is eternal.",
        # Christian mom
        "Christian mom: raising arrows for a purpose greater than herself.",
        "My greatest ministry is the children who call me Mom.",
        "Motherhood is my mission field.",
        # Christian college student
        "Campus is my mission field. Faith is my foundation.",
        "Christian student: learning to think, choosing to believe.",
        # Christian entrepreneur
        "Built on faith. Driven by purpose. Accountable to grace.",
        "Business is my ministry. Excellence is my worship.",
    ],
    "Children's Themed Rooms": [
        # Safari
        "Wild at heart. Brave by nature.",
        "Born to explore the wild, wonderful world.",
        "Adventure is out there — start in your own backyard.",
        # Ocean
        "Dream deep. Swim far. Wonder always.",
        "The ocean is calling, little one.",
        "Salty air and big dreams.",
        # Space
        "Reach for the stars — they are closer than you think.",
        "The universe is big enough for every dream you have.",
        "Future astronaut in training.",
        # Dinosaur
        "Roar with courage. Stomp with kindness.",
        "Tiny but mighty — just like T-Rex.",
        # Bible verse nursery
        "You are fearfully and wonderfully made.",
        "Before you were born, you were known and loved.",
        "Children are a gift — a blessing beyond measure.",
        # General kids
        "You are braver, stronger, and smarter than you think.",
        "Dream big, little one. The world needs your gift.",
        "Be kind. Be curious. Be wonderfully, completely you.",
    ],
    "Open When Posters": [
        "Open when you feel like quitting: You have come too far to stop now. Rest if you must, but do not quit.",
        "Open when you are lonely: You are never truly alone — you are loved more than you know.",
        "Open when you need courage: Courage is not the absence of fear. It is deciding something matters more.",
        "Open when you miss home: Home is not just a place — it is the people and the love that shaped you.",
        "Open when life feels hard: Hard seasons do not last. Strong people do. You are one of them.",
        "Open when you doubt yourself: Every great person once sat where you are sitting, doubting everything.",
        "Open when you need a reminder: You are enough. You are loved. You are not alone.",
        "Open when you want to give up: The story is not over. The best chapters often come after the hardest ones.",
    ],
    "Healthcare Specialists": [
        # ICU / NICU
        "ICU nurses: standing guard over the most fragile moments of life.",
        "NICU nurse: holding the tiniest lives with the steadiest hands.",
        "Every patient who leaves the ICU carries a piece of the nurse who fought for them.",
        # PT / OT
        "Physical therapists: turning recovery into a comeback story, one step at a time.",
        "Occupational therapy: teaching life how to resume after life paused.",
        "PT: where pain becomes progress and progress becomes possible.",
        # Pharmacist
        "Pharmacists: the last line of defense between patient and error.",
        "Behind every safe medication is a pharmacist who checked twice.",
        # Radiologist / respiratory
        "Radiologists: seeing what the eye cannot, diagnosing what words cannot describe.",
        "Respiratory therapists: the breath between crisis and recovery.",
        "Every specialist in healthcare chose a harder path — because the patient needed them to.",
    ],
    "Home Gym & Fitness": [
        "This is where excuses come to die.",
        "Train hard. Rest well. Rise stronger.",
        "No days off from becoming better.",
        "The gym is not punishment. It is a promise you keep to yourself.",
        "Running: the cheapest therapy with the best results.",
        "26.2 miles of proof that you can do hard things.",
        "CrossFit: where you find out what you are actually made of.",
        "Bodybuilding is the art of becoming what you eat, lift, and believe.",
        "Discipline is the bridge between goal and accomplishment.",
        "Home gym: no commute, no excuses, no limits.",
        "Stronger every single day.",
        "The only bad workout is the one you skipped.",
    ],
    "Digital Products": [
        "Your vision board is just the beginning — now execute.",
        "A goal without a plan is just a wish. Write it down.",
        "Track your habits. Track your life.",
        "Prayer journal: where conversation with God becomes visible.",
        "Scripture study: the more you read, the more you find.",
        "What you consistently do shapes who you consistently become.",
        "Manifest it. Plan it. Execute it. Review it. Repeat.",
        "Gratitude turns ordinary days into extraordinary ones.",
        "Your future self is reading the habits you set today.",
    ],
    "Dental School Journey Map": [
        "Shadowing → DAT → Interview → Acceptance → Year One → Clinic → Boards → DDS → Practice Owner.",
        "Every step of the dental journey is earned. None of it is given.",
        "The path to DDS is long, hard, and absolutely worth it.",
        "Pre-dental grind today. White coat moment tomorrow.",
        "DAT done. Dental school next. Practice someday. Dream always.",
        "The dental school journey is not just a degree — it is a transformation.",
        "From the library to the clinic to the practice — every step matters.",
        "Your name will be on that door. Keep going.",
    ],
    "Christian Prayers by Situation": [
        # Anxiety prayer
        "Lord, still the storm inside me. Let your peace be my anchor.",
        "When anxiety rises, let my trust in you rise higher.",
        "I cast my worries upon you — carry what I cannot hold alone.",
        # Student / exam prayer
        "Guide my mind, steady my hands, and let your wisdom speak through me.",
        "Lord, let every hour of study be met with your clarity and grace.",
        # Dental school / medical prayer
        "Lord, guide these hands to heal, these eyes to see, and this heart to serve.",
        "In every patient, let me see a life worth fighting for.",
        # New mother prayer
        "Lord, give me the strength, wisdom, and grace this little life deserves.",
        "Thank you for the miracle I now hold. Guide every step I take for them.",
        # Cancer recovery prayer
        "Lord, heal what only you can reach. Let your peace go before me.",
        "In the middle of the hardest battle, I choose faith over fear.",
        # Marriage prayer
        "Lord, keep our love rooted in grace and growing through every season.",
        "Bless this marriage with patience, laughter, and unshakeable faith.",
        # Grief prayer
        "Lord, hold what I cannot carry. Be near to my broken heart.",
        "In grief, let me feel your presence more than the pain.",
        # New job / financial
        "Lord, let my work be a blessing — to others and to the life you have given me.",
        "Open doors no one else can open. Close the ones that do not serve your plan.",
    ],
}


def get_quotes(category: str, count: int = 5) -> list[str]:
    """Return `count` unique random quotes from the given category."""
    pool = QUOTE_LIBRARY.get(category, [])
    if not pool:
        return []
    return random.sample(pool, min(count, len(pool)))
