/**
 * `<MfaChallengeHost/>` — renders the ONE open MFA challenge (raised by the api
 * client on `403 mfa_required`). Mounted once by the seed AuthProviders, so no
 * product code is needed. Renders nothing while no challenge is open.
 */
import * as React from 'react';

import { mfaChallenge } from '../../mfaChallenge';
import { MfaChallengeDialog } from './MfaChallengeDialog';

export function MfaChallengeHost() {
  const request = React.useSyncExternalStore(mfaChallenge.subscribe, mfaChallenge.getCurrent, mfaChallenge.getCurrent);
  if (!request) return null;
  return (
    <MfaChallengeDialog
      open
      enrolled={request.enrolled}
      api={request.api}
      onVerified={async (result) => {
        await request.onVerified(result);
        mfaChallenge.settle(true);
      }}
      onCancel={() => mfaChallenge.settle(false)}
    />
  );
}
