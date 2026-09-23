/**
 * Legal-entity footer block (14 §Mega-footer). The owner has not supplied a
 * razão social / CNPJ / registered address yet — inventing one would be a
 * P7 violation ("never fabricate ... certifications"), so every field
 * starts `null` and the footer omits the line entirely rather than show a
 * placeholder.
 *
 * NOC-REMEDIATE[content]: fill in the real legal-entity fields (razão
 * social, CNPJ, endereço) once the owner supplies them, then drop this
 * marker.
 */
export const legalEntity: {
  razaoSocial: string | null;
  cnpj: string | null;
  address: string | null;
} = {
  razaoSocial: null,
  cnpj: null,
  address: null,
};
