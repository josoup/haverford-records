export interface AthleteSeason {
  id: string;
  name: string;
  sport: string;
  sportSlug: string;
  season: string;
  jersey: string | null;
  position: string | null;
  height: string | null;
  classYear: string | null;
  hometown: string | null;
  state: string | null;
  highSchool: string | null;
  bioUrl: string | null;
}

export interface AthleteData {
  generatedFrom: string;
  athleteSeasons: AthleteSeason[];
  sources: { file: string; athletes: number; sport: string; season: string }[];
}
