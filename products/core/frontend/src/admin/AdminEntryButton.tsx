import { useNavigate } from 'react-router-dom';

/** Dashboard shortcut into the admin panel. Lives in the admin chunk so the admin path never ships in the main bundle. */
export default function AdminEntryButton() {
  const navigate = useNavigate();
  return (
    <button
      className="h-9 rounded-md bg-primary text-primary-foreground px-4 text-sm font-medium hover:bg-primary/90 transition-colors"
      onClick={() => navigate('/admin')}
    >
      Painel admin
    </button>
  );
}
