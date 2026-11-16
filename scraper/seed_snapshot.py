"""
Builds data/legislators.json from a snapshot of https://www.azleg.gov/memberroster/
taken 2026-11-09 (57th Legislature, session id 130).

Use this only to bootstrap the prototype. From then on, run scrape_roster.py,
which reads the live page and overwrites the same file.
"""
import json
from datetime import date
from pathlib import Path

LEGISLATURE = 57
SESSION_ID = 130
SNAPSHOT_DATE = "2026-11-09"

# (first/full name, leadership title, district, party, email handle, room, phone ext, legislator id, note)
HOUSE = [
    ("Anna Abeytia", "", 24, "D", "AABEYTIA", "121", "3501", 2366, ""),
    ("Cesar Aguilar", "", 26, "D", "CAGUILAR", "122", "3953", 2293, ""),
    ("Sylvia Allen", "", 7, "R", "SALLEN", "302", "3579", 2419, ""),
    ("Lorena Austin", "", 9, "D", "LAUSTIN", "124", "3968", 2343, ""),
    ("Leo Biasiucci", "", 30, "R", "LBIASIUCCI", "110", "3018", 2294, ""),
    ("Walt Blackman", "", 7, "R", "WBLACKMAN", "224", "3244", 2356, ""),
    ("Seth Blattman", "", 9, "D", "SBLATTMAN", "125", "3996", 2295, ""),
    ("Selina Bliss", "", 1, "R", "SBLISS", "306", "4018", 2296, ""),
    ("Michael Carbone", "Majority Leader", 25, "R", "MCARBONE", "208", "4038", 2298, ""),
    ("Neal Carter", "Speaker Pro Tempore", 15, "R", "NCARTER", "204", "5761", 2297, ""),
    ("Pamela Carter", "", 4, "R", "PCARTER", "304", "3153", 2354, ""),
    ("Junelle Cavero", "", 11, "D", "JCAVERO", "325", "3285", 2351, ""),
    ("Joseph Chaplik", "", 3, "R", "", "", "", 2299, "Resigned on 3/2 to run for Congress"),
    ("Janeen Connolly", "", 8, "D", "JCONNOLLY", "118", "3300", 2357, ""),
    ("Lupe Contreras", "", 22, "D", "LCONTRERAS", "331", "5284", 2301, ""),
    ("Patty Contreras", "", 12, "D", "PCONTRERAS", "126", "4057", 2302, ""),
    ("Quantá Crews", "Minority Whip", 26, "D", "QCREWS", "321", "3256", 2345, ""),
    ("Oscar De Los Santos", "Minority Leader", 11, "D", "ODELOSSANTOS", "320", "4098", 2303, ""),
    ("Lupe Diaz", "", 19, "R", "LDIAZ", "313", "4852", 2304, ""),
    ("Lisa Fink", "", 27, "R", "LFINK", "345", "3516", 2369, ""),
    ("Brian Garcia", "", 8, "D", "BGARCIA", "335", "3329", 2358, ""),
    ("John Gillette", "", 30, "R", "JGILLETTE", "130", "4100", 2306, ""),
    ("Matt Gress", "", 4, "R", "MGRESS", "205", "4105", 2308, ""),
    ("Gail Griffin", "", 19, "R", "GGRIFFIN", "225", "5895", 2309, ""),
    ("Nancy Gutierrez", "Assistant Minority Leader", 18, "D", "NGUTIERREZ", "330", "4134", 2310, ""),
    ("Ralph Heap", "", 10, "R", "RHEAP", "309", "3381", 2360, ""),
    ("Laurin Hendrix", "", 14, "R", "LHENDRIX", "114", "4209", 2316, ""),
    ("Alma Hernandez", "", 20, "D", "AHERNANDEZ", "338", "3136", 2312, ""),
    ("Consuelo Hernandez", "", 21, "D", "CHERNANDEZ", "117", "3523", 2313, ""),
    ("Lydia Hernandez", "", 24, "D", "LHERNANDEZ", "334", "3553", 2314, ""),
    ("Rachel Keshel", "", 17, "R", "RKESHEL", "303", "3558", 2317, ""),
    ("Alexander Kolodin", "", 3, "R", "AKOLODIN", "323", "3560", 2318, ""),
    ("Nick Kupper", "", 25, "R", "NKUPPER", "312", "3512", 2367, ""),
    ("Sarah Liguori", "", 5, "D", "SLIGUORI", "115", "3264", 2347, ""),
    ("David Livingston", "", 28, "R", "DLIVINGSTON", "222", "4178", 2319, ""),
    ("Chris Lopez", "", 16, "R", "CLOPEZ", "310", "3445", 2364, ""),
    ("Elda Luna-Nájera", "", 22, "D", "ELUNA-NAJERA", "332", "3881", 2349, ""),
    ("Aaron Márquez", "", 5, "D", "AMARQUEZ", "123", "3179", 2355, ""),
    ("David Marshall, Sr.", "", 7, "R", "", "", "", 2321, "Resigned on 4/17 with no reason given"),
    ("Teresa Martinez", "", 16, "R", "TMARTINEZ", "129", "3158", 2323, ""),
    ("Christopher Mathis", "", 18, "D", "CMATHIS", "337", "3138", 2322, ""),
    ("Steve Montenegro", "Speaker", 29, "R", "SMONTENEGRO", "223", "3635", 2325, ""),
    ("Quang H Nguyen", "", 1, "R", "QNGUYEN", "226", "3258", 2326, ""),
    ("Justin Olson", "", 10, "R", "JOLSON", "113", "3376", 2359, ""),
    ("Michele Peña", "", 23, "R", "MPENA", "341", "3696", 2331, ""),
    ("Mae Peshlakai", "", 6, "D", "MPESHLAKAI", "116", "3708", 2332, ""),
    ("Beverly Pingerelli", "", 28, "R", "BPINGERELLI", "131", "3396", 2333, ""),
    ("Khyl Powell", "", 14, "R", "KPOWELL", "342", "3415", 2362, ""),
    ("Cody Reim", "", 3, "R", "CREIM", "318", "3436", 2417, ""),
    ("Tony Rivero", "", 27, "R", "TRIVERO", "112", "3528", 2368, ""),
    ("Mariana Sandoval", "", 23, "D", "MSANDOVAL", "326", "3740", 2334, ""),
    ("Stephanie Simacek", "", 2, "D", "SSIMACEK", "120", "3083", 2353, ""),
    ("Stephanie Stahl Hamilton", "", 21, "D", "SSTAHLHAMILTON", "333", "3279", 2338, ""),
    ("James Taylor", "", 29, "R", "JTAYLOR", "344", "3564", 2370, ""),
    ("Stacey Travers", "Minority Whip", 12, "D", "STRAVERS", "322", "3917", 2340, ""),
    ("Myron Tsosie", "", 6, "D", "MTSOSIE", "339", "3157", 2341, ""),
    ("Betty J Villegas", "", 20, "D", "BVILLEGAS", "324", "3027", 2346, ""),
    ("Kevin Volk", "", 17, "D", "KVOLK", "119", "3498", 2365, ""),
    ("Michael Way", "", 15, "R", "MWAY", "308", "3433", 2363, ""),
    ("Jeff Weninger", "", 13, "R", "JWENINGER", "316", "3392", 2361, ""),
    ("Julie Willoughby", "Majority Whip", 13, "R", "JWILLOUGHBY", "207", "4153", 2344, ""),
    ("Justin Wilmeth", "", 2, "R", "JWILMETH", "111", "5044", 2342, ""),
]

SENATE = [
    ("Lela Alston", "Minority Caucus Chair", 5, "D", "LALSTON", "315", "5829", 2371, ""),
    ("Hildy Angius", "", 30, "R", "HANGIUS", "302", "5051", 2373, ""),
    ("Shawnna Bolick", "", 2, "R", "SBOLICK", "307", "3314", 2400, ""),
    ("Flavio Bravo", "", 26, "D", "FBRAVO", "313", "4033", 2399, ""),
    ("Eva Burch", "", 9, "D", "", "", "", 2374, "Resigned 03/14/2025"),
    ("Frank Carroll", "Majority Whip", 28, "R", "FCARROLL", "212", "3249", 2375, ""),
    ("Eva Diaz", "", 22, "D", "EVA.DIAZ", "313", "3473", 2376, ""),
    ('Timothy "Tim" Dunn', "", 25, "R", "TDUNN", "310", "4139", 2388, ""),
    ('Denise "Mitzi" Epstein', "", 12, "D", "MEPSTEIN", "315", "4870", 2377, ""),
    ("David C. Farnsworth", "", 10, "R", "DFARNSWORTH", "200", "3387", 2378, ""),
    ("Brian Fernandez", "", 23, "D", "BFERNANDEZ", "312", "3098", 2379, ""),
    ("Mark Finchem", "", 1, "R", "MFINCHEM", "304", "3631", 2372, ""),
    ("Rosanna Gabaldón", "Minority Whip", 21, "D", "RGABALDON", "305", "3424", 2380, ""),
    ("Sally Ann Gonzales", "", 20, "D", "SGONZALES", "314", "3278", 2381, ""),
    ("David Gowan", "", 19, "R", "DGOWAN", "300", "5154", 2382, ""),
    ("Theresa Hatathlie", "", 6, "D", "THATATHLIE", "311", "5160", 2383, ""),
    ("Jake Hoffman", "", 15, "R", "JAKE.HOFFMAN", "306", "3292", 2385, ""),
    ("John Kavanagh", "Majority Leader", 3, "R", "JKAVANAGH", "212", "5170", 2386, ""),
    ("Lauren Kuby", "", 8, "D", "LKUBY", "311", "4124", 2390, ""),
    ('Venden "Vince" Leach', "", 17, "R", "VLEACH", "303", "3694", 2398, ""),
    ("J.D. Mesnard", "", 13, "R", "JMESNARD", "309", "4481", 2391, ""),
    ("Catherine Miranda", "Assistant Minority Leader", 11, "D", "CMIRANDA", "213", "3413", 2392, ""),
    ("Analise Ortiz", "", 24, "D", "ANALISE.ORTIZ", "308", "3633", 2384, ""),
    ("Kevin Payne", "", 27, "R", "KPAYNE", "302", "4854", 2387, ""),
    ("Warren Petersen", "President", 14, "R", "WPETERSEN", "205", "4136", 2393, ""),
    ("Wendy Rogers", "", 7, "R", "WROGERS", "304", "3042", 2394, ""),
    ("Kiana Sears", "", 9, "D", "KSEARS", "314", "3374", 2415, ""),
    ("Janae Shamp", "", 29, "R", "JSHAMP", "303", "3499", 2395, ""),
    ('Thomas "T.J." Shope', "President Pro Tempore", 16, "R", "TSHOPE", "212", "3012", 2396, ""),
    ("Priya Sundareshan", "Minority Leader", 18, "D", "PSUNDARESHAN", "213", "3437", 2397, ""),
    ("Carine Werner", "", 4, "R", "CWERNER", "301", "3673", 2389, ""),
]


def build(rows, chamber):
    body = "House" if chamber == "H" else "Senate"
    out = []
    for name, title, dist, party, handle, room, ext, lid, note in rows:
        active = bool(handle)
        out.append({
            "id": lid,
            "name": name,
            "chamber": chamber,
            "chamber_name": "House" if chamber == "H" else "Senate",
            "district": dist,
            "party": party,
            "leadership_title": title or None,
            "email": f"{handle.lower()}@azleg.gov" if handle else None,
            "room": f"Room {room}" if room else None,
            "phone": f"(602) 926-{ext}" if ext else None,
            "status": "active" if active else "resigned",
            "status_note": note or None,
            "committees": [],
            "profile_url": f"https://www.azleg.gov/{body}/{body}-member/?legislature={LEGISLATURE}&session={SESSION_ID}&legislator={lid}",
            "source": "azleg.gov/memberroster",
        })
    return out


def validate(members):
    active = [m for m in members if m["status"] == "active"]
    sen = [m for m in active if m["chamber"] == "S"]
    rep = [m for m in active if m["chamber"] == "H"]
    assert len(sen) == 30, f"expected 30 active senators, got {len(sen)}"
    assert len(rep) == 60, f"expected 60 active representatives, got {len(rep)}"
    for d in range(1, 31):
        s = [m for m in sen if m["district"] == d]
        r = [m for m in rep if m["district"] == d]
        assert len(s) == 1 and len(r) == 2, f"district {d}: {len(s)} senator(s), {len(r)} rep(s)"
    return len(sen), len(rep)


if __name__ == "__main__":
    members = build(SENATE, "S") + build(HOUSE, "H")
    s, r = validate(members)
    payload = {
        "legislature": LEGISLATURE,
        "session_id": SESSION_ID,
        "session_label": "57th Legislature, Second Regular Session (2026)",
        "retrieved": SNAPSHOT_DATE,
        "source_url": "https://www.azleg.gov/memberroster/",
        "members": members,
    }
    out = Path(__file__).resolve().parent.parent / "data" / "legislators.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} — {s} senators, {r} representatives active, "
          f"{len(members) - s - r} resigned rows kept for history")
