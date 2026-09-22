"""
hub_essays.py
The written text for the ten curated anchor hubs.

Why a separate file. build_site_data.py is the contract: its job is to decide what
is TRUE about a record (is it self-hosted, is the licence honoured, is the date
defensible) and it should stay readable as a contract. Prose is not a rule, and a
thousand words of history wedged into a dict of coordinates would bury the
validators that matter. So the essays live here and the builder imports them.

The structure is a plain dict: hub id -> {"description", "historicalContext"}.
build_site_data.py looks each anchor up by id and fills the two string fields on
SoundHub. A hub id with no entry here simply gets empty strings, which is already
the model default, so nothing breaks if an anchor is added before its essay is
written.

Two editorial rules, both of which cost something to keep:

1. An empty anchor still gets an essay. Aleppo, Konya and Kashgar currently hold
   zero recordings. The temptation is to hide them until they fill up. We do not,
   because a map of what open archives happen to contain is not the same as a map
   of the tradition, and showing the difference is the honest thing. The essay for
   an empty place says plainly that it is empty and why.

2. Where scholarship is contested, the text says so rather than picking the better
   story. The Amannisa Khan attribution in Kashgar is the clearest case: it is
   repeated everywhere and it does not survive a look at the sources. Writing
   "tradition holds" instead of "she collected" is one word of hedging that keeps
   the whole thing truthful.
"""

HUB_ESSAYS = {

    "fez": {
        "description": (
            "Seat of al-Ala, the Moroccan branch of the Andalusi nawba, and of a dense "
            "network of Sufi zawiyas whose sung liturgy runs alongside it."
        ),
        "historicalContext": (
            "Al-Ala is what became of the Andalusi repertoire in Morocco after the fall "
            "of al-Andalus: a suite form called the nawba, each one built on a sequence "
            "of rhythmic cycles that move from slow to fast across an evening. Eleven "
            "nawbat survive of a notional twenty-four. The written spine of the tradition "
            "is the Kunnash al-Ha'ik, a compilation of song texts assembled in the late "
            "eighteenth century that fixed in writing what had until then been carried by "
            "ear.\n\n"
            "Transmission in Fez has run through named teaching lineages rather than "
            "through any single institution, and the line most often traced runs from "
            "al-Brihi to Abdelkrim Rais. Alongside the art repertoire sits the sung "
            "liturgy of the Sufi orders, the Tijaniyya above all, whose mother zawiya is "
            "here. Since 1994 the Fes Festival of World Sacred Music has given the city an "
            "international platform; its founder, Faouzi Skali, started it as a deliberate "
            "answer to the argument that civilisations are bound to collide.\n\n"
            "What this map holds for Fez is three calls to prayer. The nawba itself is "
            "almost entirely absent from open archives, which says more about recording "
            "and licensing than about the music."
        ),
    },

    "cairo": {
        "description": (
            "The recording capital of Arab music for most of the twentieth century, and "
            "the city where tarab became a commercial repertoire."
        ),
        "historicalContext": (
            "Tarab names both a repertoire and the state it aims at: the slow, negotiated "
            "build between a singer and an audience that answers back. Its central "
            "concert form, the dawr, gave a soloist room to improvise inside a fixed "
            "framework, and the early gramophone industry in Cairo turned that practice "
            "into a catalogue.\n\n"
            "The Congress of Arab Music, held in Cairo in 1932, was the moment the "
            "scholarly world tried to fix the tradition in place. His Master's Voice "
            "recorded delegations from across the Arab world and beyond, producing 162 "
            "discs that sat largely unheard in the Bibliotheque nationale de France until "
            "an eighteen-CD edition appeared in 2015. The congress argued about tuning, "
            "notation and whether the piano belonged in Arab music, and it settled "
            "remarkably little.\n\n"
            "What survived commercial taste, after the 1930s pushed popular song toward "
            "larger orchestras and tighter arrangements, was Sufi inshad: the sung praise "
            "poetry of the orders and the mawlid festivals, which kept the older tarab "
            "aesthetic long after the record industry moved on. Five of the six recordings "
            "placed here are calls to prayer from Maadi, Giza, Khan el-Khalili and al-Azhar "
            "Park. The sixth is a walk through the mawlid of al-Rifa'i, and it is the only "
            "thing in this collection that captures a festival rather than a moment."
        ),
    },

    "aleppo": {
        "description": (
            "The northern Syrian city that taught the Arab world its muwashshah and qudud, "
            "and the clearest gap in this map."
        ),
        "historicalContext": (
            "Aleppo's reputation rested on two overlapping repertoires. The muwashshah is "
            "a strophic sung poem of Andalusi descent, held in Aleppo with unusual rigour "
            "and rhythmic complexity. The qudud halabiyya are its more popular cousin: "
            "familiar melodies, often religious in origin, refitted with secular texts and "
            "sung in gatherings.\n\n"
            "The route into that tradition ran through the mosque. Sabri Moudallal and "
            "Sabah Fakhri, the two singers who carried Aleppine song to international "
            "audiences in the second half of the twentieth century, both trained and worked "
            "as muezzins before they were concert performers, and the vocal technique "
            "transfers directly. The city also held a Jewish pizmonim tradition that shared "
            "melodies and maqam practice with its Muslim neighbours; that community left "
            "over the course of the twentieth century and the repertoire is now sung "
            "largely in Brooklyn.\n\n"
            "Since 2012 the city has been through siege, mass displacement and the "
            "destruction of much of its old quarter, including buildings where this music "
            "was performed. This hub holds nothing. Not because Aleppo recorded nothing, "
            "but because almost none of what was recorded has been released under a licence "
            "that allows it to be republished here. The empty circle is the point."
        ),
    },

    "konya": {
        "description": (
            "Rumi's burial place and the destination of the Mevlevi order, though not the "
            "city where the order's music was written."
        ),
        "historicalContext": (
            "Konya is where Jalal al-Din Rumi died in 1273 and where the order that formed "
            "around his teaching has its shrine. It is not, however, where the Mevlevi "
            "musical repertoire was composed. The ayin, the long through-composed suite "
            "that accompanies the turning ceremony, was largely written by musicians "
            "attached to the mevlevihanes of Istanbul, which functioned as the order's "
            "conservatories. The three oldest ayins in the repertoire are transmitted "
            "without a composer's name attached, and the anonymity appears to be "
            "deliberate rather than accidental.\n\n"
            "One piece has opened the ceremony for roughly three hundred and thirty years: "
            "Itri's setting of the Na't-i Sherif in makam Rast, sung before anything else "
            "happens. That continuity is unusual in any musical tradition.\n\n"
            "Law 677, passed on 30 November 1925, closed the Sufi lodges across the new "
            "Turkish republic and the ceremony went underground. It returned publicly in "
            "1953, but its legal standing on return was as a cultural performance rather "
            "than as worship, and that framing has shaped how it is staged ever since. "
            "This hub holds no recordings."
        ),
    },

    "isfahan": {
        "description": (
            "A vocal school within Persian classical music, and a lesson in how easily a "
            "mode's name is mistaken for a place."
        ),
        "historicalContext": (
            "Persian classical music is organised around the radif, an ordered body of "
            "melodic material that a student learns whole before being allowed to improvise "
            "inside it. The radif was codified in Tehran, by the Farahani family, in the "
            "later nineteenth century. Isfahan's claim is narrower and quieter: a vocal "
            "school with a recognisable style, running from Taj Esfahani through to "
            "Mohammad-Reza Shajarian, who studied that lineage closely.\n\n"
            "There is a mode called Bayat-e Esfahan, and scholars disagree about where it "
            "properly sits within the dastgah system. That disagreement is a useful warning. "
            "This collection originally placed a recording here called 'Isfahan Gazel', on "
            "the strength of the word in its title. It is a performance by Mulla Uthman "
            "al-Mawsili, born in Mosul in 1854 and died in Baghdad in 1923, cut in Istanbul "
            "around 1910. 'Isfahan' in that title is the makam, not the city. The record has "
            "been moved and the gazetteer now refuses to place any recording by the name of "
            "a mode when the surrounding words suggest the musical sense.\n\n"
            "What remains here is a recording made inside the Shah Mosque on the Naqsh-e "
            "Jahan square, which is worth hearing for the acoustic alone."
        ),
    },

    "delhi": {
        "description": (
            "Home of the Qawwal Bachchon ka Gharana, the singing lineage that traces itself "
            "to Amir Khusrau and the shrine of Nizamuddin Auliya."
        ),
        "historicalContext": (
            "Qawwali is sung at the dargah of Nizamuddin Auliya, the Chishti saint who died "
            "in 1325, and the tradition names Amir Khusrau, his disciple, as the figure who "
            "gave the form its shape. The performers attached to that shrine constitute a "
            "hereditary lineage, the Qawwal Bachchon ka Gharana, whose training passes "
            "within families rather than through schools. Thursday evening at the dargah is "
            "still when it happens.\n\n"
            "Partition in 1947 split the lineage. A substantial part of it moved to "
            "Karachi, which is where the twentieth century's most internationally famous "
            "qawwals emerged, while the shrine and the older transmission stayed in Delhi. "
            "The result is that the lineage's history is Delhi's and its fame is largely "
            "Pakistan's.\n\n"
            "One correction worth making, because it is repeated constantly: qawwali does "
            "not appear on UNESCO's Representative List of the Intangible Cultural Heritage "
            "of Humanity. Related traditions do, which is probably the source of the "
            "confusion. This hub holds a single recording, a call to prayer from Old Delhi."
        ),
    },

    "kashgar": {
        "description": (
            "Western anchor of the Uyghur Twelve Muqam, and the place on this map with the "
            "most contested history."
        ),
        "historicalContext": (
            "The Twelve Muqam is a cycle of long suites, each running through sung poetry, "
            "instrumental sections and dance rhythms, and a complete performance of all "
            "twelve takes far longer than any concert format allows. It was inscribed on "
            "UNESCO's Representative List in 2008, having been proclaimed a Masterpiece "
            "three years earlier.\n\n"
            "The standard origin story credits Amannisa Khan, a sixteenth-century consort, "
            "with collecting and ordering the muqam. That attribution does not hold up. "
            "The nineteenth-century source usually cited for it, written in 1854, mentions "
            "her without saying anything about the muqam at all, and the collecting story "
            "appears to enter circulation through a stage play written in 1983 (Anderson, "
            "Asian Music 43:1, 2012). What is documented is a state collection and notation "
            "project beginning in the 1950s, which recorded surviving masters and produced "
            "the fixed version most performances now follow. Fixing an oral repertoire in "
            "notation preserves it and narrows it at the same time.\n\n"
            "This hub holds no recordings. Openly licensed Uyghur material is very scarce, "
            "and the reasons for that scarcity are not neutral ones."
        ),
    },

    "istanbul": {
        "description": (
            "Where Ottoman makam was composed, taught and first recorded, and by a wide "
            "margin the best-represented place on this map."
        ),
        "historicalContext": (
            "Ottoman art music is built on makam, a melodic system specifying not just a "
            "scale but the paths through it, and usul, rhythmic cycles that can run to "
            "dozens of beats. The repertoire was written and taught in the city's palace "
            "circles and, just as importantly, in its mevlevihanes: the Mevlevi lodges "
            "functioned as conservatories, and most of the order's ceremonial music comes "
            "from here rather than from Konya.\n\n"
            "Recording arrived early. Tanburi Cemil Bey, whose playing changed what the "
            "tanbur and the kemence were thought capable of, recorded for the Orfeon label "
            "between roughly 1910 and 1914, and those sides are still the reference point "
            "for the style. A decade later Law 677 closed the lodges, and the institutional "
            "base of the music had to be rebuilt in a secular republic that was not sure it "
            "wanted it.\n\n"
            "Istanbul is over-represented here, and the reason is worth stating. Six of its "
            "instrumental recordings come from a research corpus assembled at Universitat "
            "Pompeu Fabra in Barcelona and released openly. No comparable corpus exists for "
            "any other city on this map. What you are looking at is not the shape of the "
            "tradition; it is the shape of who decided to publish."
        ),
    },

    "marrakech": {
        "description": (
            "Gnawa city, where a sub-Saharan ritual repertoire took root inside a Moroccan "
            "Sufi frame."
        ),
        "historicalContext": (
            "The Gnawa are descended from people brought north across the Sahara into "
            "Morocco, largely through slavery, and their ceremony carries that history in "
            "its structure. The central ritual is the lila, an all-night ceremony organised "
            "around the seven mluk, sets of spirits addressed in sequence, each with its own "
            "colour, incense and body of songs. The music is carried by the guembri, a "
            "three-stringed bass lute, and the qraqeb, iron castanets whose pattern drives "
            "the whole night forward.\n\n"
            "Marrakech also anchors the Seven Saints circuit, a pilgrimage route around "
            "seven tombs in the city. It feels ancient and is not: it was assembled in the "
            "seventeenth century under state patronage, which is a reminder that traditions "
            "are sometimes founded on purpose.\n\n"
            "Since 1998 the Gnaoua festival in Essaouira has pulled the repertoire onto "
            "international stages and into collaborations with jazz and rock musicians, a "
            "shift that has been good for the musicians' livelihoods and contested in "
            "everything else. This hub holds one call to prayer."
        ),
    },

    "shusha": {
        "description": (
            "The mountain town in Karabakh that produced a distinct school of mugham and "
            "its most-recorded singer."
        ),
        "historicalContext": (
            "Mugham is the Azerbaijani modal tradition, sung by a khanende who also plays "
            "the frame drum, accompanied by tar and kamancha, alternating measured song "
            "with long unmetred improvisation on classical poetry. Shusha, founded in the "
            "eighteenth century and set high in the Karabakh mountains, held the school "
            "that trained much of the tradition's first recorded generation.\n\n"
            "Jabbar Garyagdioglu was born there on 31 March 1861 and died in Baku on 20 "
            "April 1944. He trained in the singing school run by Kharrat Gulu, which "
            "doubled as preparation for the Muharram passion performances, a religious "
            "route into a secular art that parallels the muezzin-to-singer path in Aleppo. "
            "His gramophone sides were cut in the years around 1906 to 1912. The three "
            "recordings here carry that range rather than a single year, deliberately: the "
            "label usually named as their publisher was not founded until 1908, so at least "
            "one commonly repeated date and imprint cannot both be right, and a range is "
            "what is actually known.\n\n"
            "Shusha was emptied and much of its fabric destroyed in the Karabakh wars of "
            "the 1990s and 2020. Three recordings are what this map can show of it."
        ),
    },
}
