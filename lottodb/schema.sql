-- ฐานข้อมูลผลสลากกินแบ่งรัฐบาล (ย้อนหลังทุกงวด ทุกรางวัล)

CREATE TABLE IF NOT EXISTS draws (
    draw_date    TEXT PRIMARY KEY,          -- 'YYYY-MM-DD' (ค.ศ.)
    draw_date_th TEXT NOT NULL,             -- '16 ตุลาคม 2569'
    ruleset      TEXT NOT NULL,             -- 'pre2015' | 'post2015'
    source       TEXT NOT NULL,             -- 'archive' | 'glo-api'
    source_url   TEXT,
    prize_count  INTEGER NOT NULL DEFAULT 0,
    anomalies    TEXT,                      -- บันทึกไว้เมื่อจำนวนรางวัลไม่ตรงโครงสร้างมาตรฐาน
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prizes (
    draw_date TEXT    NOT NULL REFERENCES draws(draw_date) ON DELETE CASCADE,
    category  TEXT    NOT NULL,             -- first, near1, front3, back3, last2, second..fifth
    slot      INTEGER NOT NULL,             -- ลำดับภายในหมวด (1-based)
    number    TEXT    NOT NULL,
    digits    INTEGER NOT NULL,
    PRIMARY KEY (draw_date, category, slot)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_prizes_number   ON prizes(number);
CREATE INDEX IF NOT EXISTS idx_prizes_cat_num  ON prizes(category, number);
CREATE INDEX IF NOT EXISTS idx_prizes_date     ON prizes(draw_date);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at    TEXT NOT NULL,
    source    TEXT NOT NULL,
    draws_new INTEGER NOT NULL,
    draws_upd INTEGER NOT NULL,
    detail    TEXT
);

-- งวดที่คลังต้นทางบันทึกวันที่ผิด เก็บไว้กันไม่ให้ sync ดึงกลับมาอีก
CREATE TABLE IF NOT EXISTS corrections (
    bad_date  TEXT PRIMARY KEY,
    good_date TEXT NOT NULL,
    reason    TEXT,
    noted_at  TEXT NOT NULL
);
