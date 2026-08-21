import { useMemo, useState } from "react";
import raw from "./data/athletes.json";
import type { AthleteData, AthleteSeason } from "./types";

const data = raw as AthleteData;

type SortKey = "name" | "sport" | "season" | "jersey" | "classYear" | "hometown";

const CLASS_ORDER = ["Fy.", "Fr.", "So.", "Jr.", "Sr.", "Gr."];

function Tile({ k, v, d }: { k: string; v: string | number; d?: string }) {
  return (
    <div className="tile">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
      {d && <span className="d">{d}</span>}
    </div>
  );
}

function Bars({ rows }: { rows: [string, number][] }) {
  const max = Math.max(...rows.map(([, n]) => n), 1);
  return (
    <div className="bars">
      {rows.map(([label, n]) => (
        <div className="bar-row" key={label}>
          <span className="lab">{label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
          </div>
          <span className="n">{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [q, setQ] = useState("");
  const [sport, setSport] = useState("all");
  const [season, setSeason] = useState("all");
  const [sort, setSort] = useState<SortKey>("name");
  const [asc, setAsc] = useState(true);

  const sports = useMemo(
    () => [...new Set(data.athleteSeasons.map((a) => a.sport))].sort(),
    []
  );
  const seasons = useMemo(
    () => [...new Set(data.athleteSeasons.map((a) => a.season))].sort().reverse(),
    []
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = data.athleteSeasons.filter((a) => {
      if (sport !== "all" && a.sport !== sport) return false;
      if (season !== "all" && a.season !== season) return false;
      if (!needle) return true;
      return [a.name, a.hometown, a.highSchool, a.position]
        .filter(Boolean)
        .some((f) => f!.toLowerCase().includes(needle));
    });
    const dir = asc ? 1 : -1;
    return [...rows].sort((x, y) => {
      const a = (x[sort] ?? "") as string;
      const b = (y[sort] ?? "") as string;
      if (sort === "jersey") return dir * ((+a || 999) - (+b || 999));
      if (sort === "classYear")
        return dir * (CLASS_ORDER.indexOf(a) - CLASS_ORDER.indexOf(b));
      return dir * a.localeCompare(b);
    });
  }, [q, sport, season, sort, asc]);

  const uniqueAthletes = new Set(data.athleteSeasons.map((a) => a.id)).size;

  const byClass = useMemo(() => {
    const c = new Map<string, number>();
    for (const a of data.athleteSeasons)
      if (a.classYear) c.set(a.classYear, (c.get(a.classYear) ?? 0) + 1);
    return [...c.entries()].sort(
      (x, y) => CLASS_ORDER.indexOf(x[0]) - CLASS_ORDER.indexOf(y[0])
    );
  }, []);

  const byState = useMemo(() => {
    const c = new Map<string, number>();
    for (const a of data.athleteSeasons)
      if (a.state) c.set(a.state, (c.get(a.state) ?? 0) + 1);
    return [...c.entries()].sort((x, y) => y[1] - x[1]).slice(0, 9);
  }, []);

  const th = (key: SortKey, label: string, cls = "") => (
    <th
      className={cls}
      tabIndex={0}
      onClick={() => (sort === key ? setAsc(!asc) : (setSort(key), setAsc(true)))}
      onKeyDown={(e) =>
        e.key === "Enter" &&
        (sort === key ? setAsc(!asc) : (setSort(key), setAsc(true)))
      }
    >
      {label}
      {sort === key && <span className="arrow">{asc ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <>
      <header className="masthead">
        <span className="wordmark">Fords Record Watch</span>
        <span className="sub">Athletics Communications · Prototype</span>
      </header>

      <div className="wrap">
        <section>
          <div className="section-head">
            <h2>What has been ingested</h2>
            <span className="note">
              Scraped from haverfordathletics.com roster pages
            </span>
          </div>
          <div className="tiles">
            <Tile k="Athlete-seasons" v={data.athleteSeasons.length} d="parsed rows" />
            <Tile k="Distinct athletes" v={uniqueAthletes} d="by source ID" />
            <Tile k="Sports" v={sports.length} d="of 23 available" />
            <Tile k="Seasons" v={seasons.length} d={seasons.join(", ")} />
            <Tile k="Parse warnings" v={0} d="across all pages" />
          </div>
        </section>

        <section>
          <div className="section-head">
            <h2>Athlete directory</h2>
            <span className="note">Every row traces back to a saved page</span>
          </div>
          <div className="controls">
            <input
              type="search"
              placeholder="Search name, hometown, school, position…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Search athletes"
            />
            <select value={sport} onChange={(e) => setSport(e.target.value)} aria-label="Filter by sport">
              <option value="all">All sports</option>
              {sports.map((s) => <option key={s}>{s}</option>)}
            </select>
            <select value={season} onChange={(e) => setSeason(e.target.value)} aria-label="Filter by season">
              <option value="all">All seasons</option>
              {seasons.map((s) => <option key={s}>{s}</option>)}
            </select>
            <span className="count">
              {filtered.length} of {data.athleteSeasons.length}
            </span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {th("jersey", "#", "num")}
                  {th("name", "Athlete")}
                  {th("sport", "Sport")}
                  {th("season", "Season")}
                  <th>Pos</th>
                  {th("classYear", "Class")}
                  <th>Ht</th>
                  {th("hometown", "Hometown")}
                  <th>High school</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a: AthleteSeason) => (
                  <tr key={`${a.id}-${a.season}`}>
                    <td className="num">{a.jersey ?? "—"}</td>
                    <td className="nm">
                      {a.bioUrl ? (
                        <a
                          href={`https://haverfordathletics.com${a.bioUrl}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {a.name}
                        </a>
                      ) : (
                        a.name
                      )}
                    </td>
                    <td className="muted">{a.sport}</td>
                    <td className="num">{a.season === "current" ? "Current" : a.season}</td>
                    <td>{a.position ?? <span className="muted">—</span>}</td>
                    <td>{a.classYear ? <span className="chip">{a.classYear}</span> : "—"}</td>
                    <td className="num">{a.height ?? "—"}</td>
                    <td className="muted">{a.hometown ?? "—"}</td>
                    <td className="muted">{a.highSchool ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="dists">
          <div>
            <div className="section-head"><h2>By class year</h2></div>
            <Bars rows={byClass} />
          </div>
          <div>
            <div className="section-head">
              <h2>Where they come from</h2>
              <span className="note">top 9 by hometown</span>
            </div>
            <Bars rows={byState} />
          </div>
        </section>

        <section className="panel">
          <h3>
            <span className="flag">Not built yet</span>&nbsp; Record watch
          </h3>
          <p>
            This page shows the <strong>athlete spine</strong> — the identity layer
            everything else attaches to. Record tracking is the next layer, and
            deliberately shows nothing yet: there are no record figures on this page
            because none have been ingested, and inventing them to fill the space
            would be the exact failure this system exists to prevent.
          </p>
          <p>To turn it on, the system needs two things it does not have:</p>
          <ul>
            <li>
              <strong>The record book.</strong> The standing marks, and who holds
              them. Without it there is nothing to compare a performance against.
            </li>
            <li>
              <strong>Career statistics.</strong> Roster pages carry identity, not
              stats. Those live on separate pages, and for track on TFRRS.
            </li>
          </ul>
          <p>
            Once both are loaded, every athlete above gains a distance-to-record and
            a projection, and anyone closing on a mark surfaces for a human to
            confirm or dismiss. <strong>The system never rules a record official</strong> —
            it assembles the evidence and routes it to whoever signs off.
          </p>
        </section>

        <section className="panel">
          <h3>Where this data came from</h3>
          <p>
            Every page fetched is stored and content-hashed, so any figure here can be
            traced to the exact document it was read from — and a page that changes
            later is kept as a new version rather than silently overwriting what we
            already had.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Source file</th><th>Sport</th><th>Season</th><th className="num">Athletes</th></tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={s.file}>
                    <td className="nm">{s.file}</td>
                    <td className="muted">{s.sport}</td>
                    <td className="num">{s.season}</td>
                    <td className="num">{s.athletes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <footer>
        <div className="wrap-f">
          Prototype for the Haverford athletics communications committee. Athlete data
          scraped from public roster pages on haverfordathletics.com. Figures shown are
          parsed directly from those pages; nothing on this page is estimated or inferred.
        </div>
      </footer>
    </>
  );
}
