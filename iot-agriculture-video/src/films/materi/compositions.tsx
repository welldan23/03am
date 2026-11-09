import { FilmSingleScene, FilmTimeline } from '../../compositions/Film';
import { MATERI_FILM } from '.';

/** Komposisi film 8 menit. Props hanya data JSON (sceneId) — definisi film diimpor langsung. */
export const MateriTimeline: React.FC = () => <FilmTimeline film={MATERI_FILM} />;
export const MateriScene: React.FC<{ sceneId: string }> = ({ sceneId }) => <FilmSingleScene film={MATERI_FILM} sceneId={sceneId} />;
