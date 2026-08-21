import type { AthleteSeason } from "./types";

const SITE = "https://haverfordathletics.com";

function initials(name: string) {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p.at(-1)?.[0] ?? "")).toUpperCase();
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="field">
      <span className="field-k">{label}</span>
      <span className="field-v">{value || <span className="muted">Not recorded</span>}</span>
    </div>
  );
}

/** One athlete's whole known career: every season we hold for their source ID. */
export default function AthleteDetail({
  seasons,
  onBack,
}: {
  seasons: AthleteSeason[];
  onBack: () => void;
}) {
  // Newest first, so the most recent season leads.
  const career = [...seasons].sort((a, b) => b.season.localeCompare(a.season));
  const latest = career[0];
  const sports = [...new Set(career.map((s) => s.sport))];

  return (
    <section className="detail">
      <button className="back" onClick={onBack}>
        ← All athletes
      </button>

      <div className="detail-head">
        <div className="avatar">
          <span className="avatar-initials">{initials(latest.name)}</span>
          {latest.headshotUrl && (
            <img
              src={`${SITE}${latest.headshotUrl}`}
              alt=""
              onError={(e) => (e.currentTarget.style.display = "none")}
            />
          )}
        </div>
        <div className="detail-id">
          <h2>{latest.name}</h2>
          <p className="detail-sub">
            {sports.join(" · ")}
            {latest.jersey && <> · #{latest.jersey}</>}
          </p>
          {latest.bioUrl && (
            <a className="ext" href={`${SITE}${latest.bioUrl}`} target="_blank" rel="noreferrer">
              Official bio page ↗
            </a>
          )}
        </div>
      </div>

      <div className="detail-grid">
        <div className="card">
          <h3>Profile</h3>
          <div className="fields">
            <Field label="Position" value={latest.position} />
            <Field label="Class" value={latest.classYear} />
            <Field label="Height" value={latest.height} />
            <Field label="Hometown" value={latest.hometown} />
            <Field label="High school" value={latest.highSchool} />
            <Field label="Source ID" value={latest.id} />
          </div>
        </div>

        <div className="card">
          <h3>
            Athletic history
            <span className="card-note">
              {career.length} season{career.length === 1 ? "" : "s"} on record
            </span>
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Season</th>
                  <th>Sport</th>
                  <th className="num">#</th>
                  <th>Pos</th>
                  <th>Class</th>
                </tr>
              </thead>
              <tbody>
                {career.map((s) => (
                  <tr key={`${s.sportSlug}-${s.season}`}>
                    <td>{s.season === "current" ? "Current" : s.season}</td>
                    <td className="muted">{s.sport}</td>
                    <td className="num">{s.jersey ?? "—"}</td>
                    <td>{s.position ?? "—"}</td>
                    <td>{s.classYear ? <span className="chip">{s.classYear}</span> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Only seasons whose roster page has been ingested appear here. The archive
            reaches back further than what is currently loaded.
          </p>
        </div>

        <div className="card wide">
          <h3>
            Biography &amp; career statistics
            <span className="flag">Not ingested</span>
          </h3>
          <p className="muted-p">
            Written bios and career stat lines live on each athlete's own page, which
            the crawler has not yet been pointed at. Rather than show a blank template
            that looks like an athlete with no history, this states plainly that the
            data is missing.
          </p>
          <p className="muted-p">
            Run <code>scripts/crawl_bios.py</code> to fetch them; every field above
            fills in from the same pipeline.
          </p>
        </div>
      </div>
    </section>
  );
}
