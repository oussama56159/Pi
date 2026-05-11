import { useMemo, useState } from 'react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import { useUIStore } from '@/stores/uiStore';
import { getActionMeta } from '@/actions/registry';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import { postActionAudit } from '@/lib/api/actions';

export default function ActionConfirmModal() {
  const pending = useUIStore((s) => s.actionConfirmation);
  const clear = useUIStore((s) => s.clearActionConfirmation);
  const [loading, setLoading] = useState(false);

  const meta = useMemo(() => (pending ? getActionMeta(pending.actionId) : null), [pending]);
  if (!pending || !meta) return null;

  const isDanger = meta.riskLevel === 'high' || meta.riskLevel === 'critical' || meta.confirmation?.style === 'danger';

  const shouldAudit = !!meta?.logging?.auditTrail;
  const audit = (outcome, { message, payload } = {}) => {
    if (!shouldAudit) return;
    void postActionAudit({
      action_id: pending.actionId,
      outcome,
      message,
      payload,
    });
  };

  const handleCancel = () => {
    audit('aborted', { payload: { context: pending?.context || null } });
    clear();
  };

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await pending.onConfirm?.();
      clear();
    } catch {
      // onConfirm already showed an error toast; just close the modal so the
      // user can see it rather than leaving a stale confirmation dialog open.
      clear();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={!!pending}
      onClose={clear}
      title="Confirm Action"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={handleCancel}>Cancel</Button>
          <Button variant={isDanger ? 'danger' : 'primary'} onClick={handleConfirm} loading={loading}>
            {isDanger ? 'Confirm' : 'Continue'}
          </Button>
        </>
      }
    >
      <div className="text-center py-4">
        {isDanger ? (
          <ShieldAlert className="w-12 h-12 text-red-400 mx-auto mb-3" />
        ) : (
          <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto mb-3" />
        )}
        <h3 className="text-lg font-semibold text-slate-100 mb-2">{meta.name}</h3>
        <p className="text-sm text-slate-400">
          {meta.confirmation?.prompt || meta.description}
        </p>
        {meta.safetyImpact && isDanger && (
          <p className="mt-3 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-2">
            {meta.safetyImpact}
          </p>
        )}
        <p className="mt-3 text-[11px] text-slate-500">
          Tip: hold <strong className="text-slate-300">Shift</strong> and click to view Action Details.
        </p>
      </div>
    </Modal>
  );
}
