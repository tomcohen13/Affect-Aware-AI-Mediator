
"""Constants used throughout the agent codebase."""

from typing import Mapping


AFFECTIVE_WINDOW_DEFAULT_LIFESPAN = 5 # seconds

NO_AFFECTIVE_WINDOW_RECEIVED_TOKEN = "<NO_AFFECTIVE_WINDOW_RECEIVED>"

SUPPORTED_MODALITIES = {
    "vision",
    "audio",
    "text"
}

HUME_EMOTIONS_LIST_TEXT = [
    "Admiration",
    "Adoration",
    "Aesthetic Appreciation",
    "Amusement",
    "Anger",
    "Annoyance",
    "Anxiety",
    "Awe",
    "Awkwardness",
    "Boredom",
    "Calmness",
    "Concentration",
    "Confusion",
    "Contemplation",
    "Contempt",
    "Contentment",
    "Craving",
    "Desire",
    "Determination",
    "Disappointment",
    "Disapproval",
    "Disgust",
    "Distress",
    "Doubt",
    "Ecstasy",
    "Embarrassment",
    "Empathic Pain",
    "Enthusiasm",
    "Entrancement",
    "Envy",
    "Excitement",
    "Fear",
    "Gratitude",
    "Guilt",
    "Horror",
    "Interest",
    "Joy",
    "Love",
    "Nostalgia",
    "Pain",
    "Pride",
    "Realization",
    "Relief",
    "Romance",
    "Sadness",
    "Sarcasm",
    "Satisfaction",
    "Shame",
    "Surprise (negative)",
    "Surprise (positive)",
    "Sympathy",
    "Tiredness",
    "Triumph",
]

HUME_EMOTIONS_LIST_VISION_AUDIO = [
    "Admiration",
    "Adoration",
    "Aesthetic Appreciation",
    "Amusement",
    "Anger",
    "Anxiety",
    "Awe",
    "Awkwardness",
    "Boredom",
    "Calmness",
    "Concentration",
    "Contemplation",
    "Confusion",
    "Contempt",
    "Contentment",
    "Craving",
    "Desire",
    "Determination",
    "Disappointment",
    "Disgust",
    "Distress",
    "Doubt",
    "Ecstasy",
    "Embarrassment",
    "Empathic Pain",
    "Entrancement",
    "Envy",
    "Excitement",
    "Fear",
    "Guilt",
    "Horror",
    "Interest",
    "Joy",
    "Love",
    "Nostalgia",
    "Pain",
    "Pride",
    "Realization",
    "Relief",
    "Romance",
    "Sadness",
    "Satisfaction",
    "Shame",
    "Surprise (negative)",
    "Surprise (positive)",
    "Sympathy",
    "Tiredness",
    "Triumph",
]

TOPIC_OPTIONS: Mapping[str, Mapping[str, str]] = {
    "ai_companions": {
        "label": "AI Companions and Relationships",
        "prompt": "Your best friend never judges you, always listens, and texts back instantly. There's just one catch: they're not human. As millions turn to AI chatbots for companionship and even romance, are we finding a lifeline for the lonely or building a digital escape pod from real human messiness?",
        "exampleTakes": "\"AI companions are a Band-Aid on a loneliness epidemic—we should fix society, not replace people with bots\" vs. \"For someone with social anxiety or disability, an AI friend might be the only judgment-free connection they have\" vs. \"This is dystopian—we're literally choosing pixels over people and calling it progress\""
    },
    "student_loans": {
        "label": "Student Loan Forgiveness",
        "prompt": "You worked three jobs to graduate debt-free. Your neighbor partied through an expensive private college and now wants taxpayers to cover the bill. Fair relief for a broken system, or a massive slap in the face to everyone who sacrificed?",
        "exampleTakes": "\"Canceling debt is economic stimulus that helps everyone—freed-up money goes back into the economy\" vs. \"I joined the military to pay for college while others took loans for luxury degrees—why should I pay twice?\" vs. \"We should forgive debt AND reimburse people who already paid—the system scammed us all\""
    },
    "ai_jobs": {
        "label": "AI Taking Jobs vs. Creating Opportunity",
        "prompt": "In ten years, will your job exist? AI is writing code, diagnosing patients, and driving trucks. Some say we're headed for mass unemployment and need checks from the government just to survive. Others see a golden age of innovation. Who's right, and what happens to the middle class either way?",
        "exampleTakes": "\"Every technological revolution killed jobs temporarily but created better ones—this is no different\" vs. \"This time IS different—AI can do cognitive work, not just manual labor, and millions will be unemployable\" vs. \"Universal basic income is inevitable when robots do everything, and that's actually liberation from wage slavery\""
    },
    "cost_of_living": {
        "label": "Gas Prices and Cost of Living",
        "prompt": "Remember when a grocery run didn't require a small loan? As families choose between filling the tank and filling the fridge, everyone's pointing fingers about who crashed the economy—and whether anyone in power actually cares.",
        "exampleTakes": "\"Corporate greed and price gouging are the real culprits—companies are posting record profits while we suffer\" vs. \"This is what happens when you print trillions of dollars and shut down pipelines—basic economics\" vs. \"Both parties serve the wealthy—regular people get squeezed no matter who's in charge\""
    },
    "chatgpt_schools": {
        "label": "ChatGPT in Schools: Cheating or Learning Tool?",
        "prompt": "Your kid just got an A on an essay written entirely by AI in 30 seconds. Is this the future of education or the death of critical thinking? Teachers are freaking out, students are clicking \"generate,\" and nobody knows if we're preparing the next generation or creating a generation that can't write a paragraph.",
        "exampleTakes": "\"Banning AI in schools is like banning calculators—we should teach kids to use tools, not pretend they don't exist\" vs. \"If students can't write without AI, they can't think critically, period—this is producing a generation of intellectual dependents\" vs. \"The real problem is we're still teaching 20th-century skills when AI makes essays obsolete anyway\""
    },
    "rent_control": {
        "label": "Rent Control and Housing Affordability",
        "prompt": "Your landlord wants to raise your rent 40%. Should the government stop them, or would that just make everything worse? Some cities are capping increases to keep people housed. Others say those same rules create the housing shortages that make rent skyrocket in the first place. Who's actually helping renters?",
        "exampleTakes": "\"Rent control keeps families in their homes and neighborhoods stable—without it, only the rich can afford cities\" vs. \"Every economist agrees rent control reduces housing supply and makes shortages worse—just build more housing\" vs. \"Landlords are hoarding property for profit while people sleep in cars—we need rent control AND to tax vacant units\""
    },
    "term_limits": {
        "label": "Term Limits for Congress",
        "prompt": "That senator has been in office since before you were born. Is that the problem with Washington, or the only reason anything gets done? Kick out the fossils or lose the only people who know how the game works?",
        "exampleTakes": "\"Term limits would end career politicians who are more loyal to donors than voters—bring in fresh blood\" vs. \"Term limits just empower lobbyists and unelected staffers who become the only people with institutional knowledge\" vs. \"We already have term limits—they're called elections, and if voters keep choosing someone, that's democracy\""
    },
    "free_speech": {
        "label": "Free Speech on Social Media",
        "prompt": "Someone posts something you know is dangerously false. Should tech companies delete it, or is that Big Brother censorship? And here's the real question: who gets to decide what counts as \"misinformation\" anyway?",
        "exampleTakes": "\"Private companies can moderate however they want—don't like it, build your own platform\" vs. \"Big Tech has monopoly power over public discourse—they're effectively government and need First Amendment obligations\" vs. \"Yesterday's 'misinformation' is today's accepted fact—we can't trust corporations or government to be truth arbiters\""
    },
    "homelessness": {
        "label": "Homelessness and Public Spaces",
        "prompt": "The park where your kids used to play is now a tent city. Do we clear it out so families feel safe again, or provide housing first and ask questions later? Business owners are losing customers, advocates say sweeps are cruel, and everyone wants solutions yesterday.",
        "exampleTakes": "\"Compassion without accountability enables addiction and mental illness—enforce laws and offer treatment, not tents\" vs. \"Sweeps just move people around without solving anything—give people housing first, then address other issues\" vs. \"We need psychiatric institutions again—many homeless people are too ill to care for themselves and need involuntary treatment\""
    },
    "presidential_terms": {
        "label": "Should Presidents Serve More Than Two Terms?",
        "prompt": "FDR did it, then we banned it. Now some want to bring it back. If a president is popular and effective, why force them out? Or is the two-term limit the one thing preventing an American dictator? When people float the idea of a third Trump term—or any president staying longer—are we talking about keeping great leadership or dismantling a safeguard that's protected democracy for 75 years?",
        "exampleTakes": "\"If people want to vote for someone, term limits are anti-democratic—let voters decide\" vs. \"The two-term limit prevents personality cults and peaceful power transfer—it's essential to democracy\" vs. \"This isn't about Trump or any person—it's about a constitutional principle that keeps presidents from becoming kings\""
    },
    "immigration": {
        "label": "Illegal Immigration and Border Security",
        "prompt": "Millions crossing the border: crisis or political theater? Should we build barriers and deport faster, or offer paths to citizenship for people already contributing to communities? And what about the towns absorbing thousands of newcomers overnight?",
        "exampleTakes": "\"Every country has borders—controlling who enters isn't racist, it's basic sovereignty and fairness to legal immigrants\" vs. \"These are human beings fleeing violence and poverty—we're a nation of immigrants, and walls betray our values\" vs. \"Both parties use immigration as a wedge issue but neither actually wants to solve it—business wants cheap labor, politicians want campaign fodder\""
    },
    "gun_rights": {
        "label": "Gun Rights vs. School Safety",
        "prompt": "Another school shooting. Parents are installing bulletproof backpacks. Some say ban assault weapons immediately. Others say that punishes law-abiding gun owners and ignores mental health. Meanwhile, kids are doing active shooter drills instead of fire drills.",
        "exampleTakes": "\"Other countries banned these weapons and shootings stopped—it's that simple, and the Second Amendment isn't unlimited\" vs. \"Millions of gun owners never hurt anyone—punishing them for criminals' actions while government can't protect us is tyranny\" vs. \"This is a mental health crisis, not a gun crisis—we've had guns forever but not mass shootings until recently\""
    },
    "parental_rights": {
        "label": "Parental Rights in Schools",
        "prompt": "Who decides what your child learns about history, sexuality, and identity—you or their teacher? Parents are storming school board meetings demanding control over curricula, while educators say politicians are turning classrooms into battlegrounds.",
        "exampleTakes": "\"I'm responsible for my child's values—schools need to teach reading and math, not controversial social topics without my consent\" vs. \"Parents don't get to censor education because they're uncomfortable—kids need to learn real history and that LGBTQ people exist\" vs. \"Both sides are weaponizing kids—let teachers teach facts and let families handle values at home\""
    },
    "political_violence": {
        "label": "Political Violence and Extremism",
        "prompt": "Political rallies now come with security screenings. Both sides say the other is radicalizing extremists and inspiring violence. Is left-wing or right-wing violence the real threat, or is asking that question already part of the problem?",
        "exampleTakes": "\"Right-wing extremism is the FBI's top domestic threat—the data is clear about where violence comes from\" vs. \"The media ignores left-wing riots and property destruction while obsessing over right-wing threats—both are wrong\" vs. \"Inflammatory rhetoric from politicians and media on both sides is radicalizing people—we need to tone down the temperature everywhere\""
    }
}