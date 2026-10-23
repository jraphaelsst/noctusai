/** Routes of the Studio skills library pages (kept out of the page modules so links don't defeat lazy loading). */
export const SKILLS_BIBLIOTECA_HREF = "/studio/biblioteca-skills";
export const skillHref = (chave: string) => `${SKILLS_BIBLIOTECA_HREF}/${encodeURIComponent(chave)}`;
