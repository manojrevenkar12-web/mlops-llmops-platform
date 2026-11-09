import { useState } from "react";
import type { SetData } from "../../app/types";
import { int } from "../../shared/format";
import { space } from "../../theme/tokens";
import { StopChart } from "./StopChart";

export function Overview({ set }: { set: SetData }) {
  const [show, setShow] = useState<"bad" | "good">("bad");
  const s = set.summary;
  return (
    <div className="board">
      <div className="chips" role="group" aria-label="Which releases to show" style={{ marginTop: 0 }}>
        <button className="chip" aria-pressed={show === "bad"} onClick={() => setShow("bad")}>
          {s.platform.bad} bad releases
        </button>
        <button className="chip" aria-pressed={show === "good"} onClick={() => setShow("good")}>
          {s.platform.good} good releases
        </button>
      </div>
      <div style={{ marginTop: space[4] }}>
        <StopChart releases={set.releases} show={show} />
      </div>
      <div className="figures">
        <div className="figure">
          <strong>
            {s.platform.bad_shipped} of {s.platform.bad}
          </strong>
          <span className="ink2">bad releases reached every customer (10% canary: {s.fixed_canary.bad_shipped}; offline only: {s.offline_only.bad_shipped})</span>
        </div>
        <div className="figure">
          <strong>
            {s.platform.good_shipped} of {s.platform.good}
          </strong>
          <span className="ink2">good releases shipped (10% canary: {s.fixed_canary.good_shipped}; offline only: {s.offline_only.good_shipped})</span>
        </div>
        <div className="figure">
          <strong>{int(s.platform.bad_exposure_requests)}</strong>
          <span className="ink2">customer requests served by bad releases before they were stopped (10% canary: {int(s.fixed_canary.bad_exposure_requests)})</span>
        </div>
      </div>
    </div>
  );
}
