import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, Stack } from '@mui/material';

type Props = {
  open: boolean;
  initialName: string;
  onCancel: () => void;
  onSave: (newName: string) => Promise<void> | void;
  saving?: boolean;
};

const RenameRunDialog: React.FC<Props> = ({ open, initialName, onCancel, onSave, saving }) => {
  const [name, setName] = React.useState(initialName);
  React.useEffect(() => { if (open) setName(initialName); }, [open, initialName]);

  return (
    <Dialog open={open} onClose={onCancel} fullWidth maxWidth="sm">
      <DialogTitle>Run umbenennen</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            autoFocus
            fullWidth
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={!!saving}>Abbrechen</Button>
        <Button onClick={() => onSave(name.trim())} variant="contained" disabled={!name.trim() || !!saving}>
          {saving ? 'Speichern…' : 'Speichern'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default RenameRunDialog;
