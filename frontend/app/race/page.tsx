"use client";

import { RacePanel } from "../../components/RacePanel";

export default function RacePage() {
  return <RacePanel infoPath="/api/race/info" streamPath="/api/race/stream" />;
}
