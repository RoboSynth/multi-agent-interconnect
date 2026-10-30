"""Keep one stopped E1-c member until its original handler proves fence rejection.

Normal takeover removes the failed member before continuing. That can cancel
the suspended handler when its AMQP channel closes. This experiment adapter
defers exactly that one removal; discovery, resume and fence activation remain
the normal transport's work. Removal is flushed before continuing the workflow.
"""
from __future__ import annotations


class DeferredPrimaryRemoval:
    def __init__(self, transport, primary_aic, backup_aic):
        self.transport, self.runtime = transport, transport.runtime
        self.primary_aic, self.backup_aic = primary_aic, backup_aic
        self.session_id = transport.session.session_id
        self.original = self.runtime.force_remove_partner
        self.pending = False
        self.deferred_count = self.removed_count = 0
        self.runtime.force_remove_partner = self.defer

    async def defer(self, aic, *, session_id=None):
        if aic != self.primary_aic:
            return await self.original(aic, session_id=session_id)
        if (session_id != self.session_id or self.transport.selected.get("database") != self.backup_aic
                or self.deferred_count):
            raise ValueError("E1-c may defer exactly one planned primary removal after backup fence confirmation")
        self.pending = True
        self.deferred_count += 1

    async def flush(self):
        if not self.pending or self.deferred_count != 1 or self.removed_count:
            raise ValueError("E1-c requires exactly one deferred primary removal")
        await self.original(self.primary_aic, session_id=self.session_id)
        self.pending = False
        self.removed_count += 1
        self.detach()
        return dict(deferred_removals=self.deferred_count, completed_removals=self.removed_count,
                    primary_aic=self.primary_aic, session_id=self.session_id)

    def detach(self):
        self.runtime.force_remove_partner = self.original
