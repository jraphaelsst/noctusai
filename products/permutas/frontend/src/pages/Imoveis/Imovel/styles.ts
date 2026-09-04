import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../../styles'

export const Container = styled.div`
  width: 100%;
  min-height: 100vh;
  background: ${color.background};
`

export const Banner = styled.div`
  background: ${color.primary};
  padding: ${spacing.xxl};
  display: flex;
  gap: ${spacing.xl};
  align-items: stretch;

  @media (max-width: ${breakpoints.tablet}) {
    flex-direction: column;
    padding: ${spacing.lg};
  }
`

export const Image = styled.div`
  background-image: url('https://placehold.co/480x360');
  background-repeat: no-repeat;
  background-size: cover;
  background-position: center;
  height: 360px;
  min-width: 480px;

  @media (max-width: ${breakpoints.tablet}) {
    min-width: 100%;
    height: 240px;
  }
`

export const Infos = styled.div`
  flex: 1;
  display: flex;
  gap: ${spacing.xl};
  padding: ${spacing.lg};
  background: ${color.cardBg};

  @media (max-width: ${breakpoints.desktop}) {
    flex-direction: column;
    gap: ${spacing.lg};
  }
`

export const DescritivoContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
`

export const Ref = styled.h1`
  font-size: 1.5rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.sm};
`

export const Valor = styled.h3`
  font-size: 2rem;
  font-weight: 600;
  color: ${color.success};
  margin-bottom: ${spacing.lg};
`

export const CorretorTipo = styled.div`
  display: flex;
  gap: ${spacing.md};
  margin-bottom: ${spacing.lg};
`

export const Corretor = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.xs} ${spacing.md};
  background: ${color.backgroundDark};
  color: ${color.text};
  font-size: 13px;
`

export const Tipo = styled.span`
  display: inline-flex;
  align-items: center;
  padding: ${spacing.xs} ${spacing.md};
  background: ${color.primary};
  color: ${color.textInverse};
  font-size: 13px;
  font-weight: 500;
`

export const Condominio = styled.p`
  font-size: 1.1rem;
  font-weight: 600;
  color: ${color.text};
  margin-bottom: ${spacing.xs};
`

export const Bairro = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.xs};
`

export const Km = styled.p`
  font-size: 14px;
  color: ${color.textMuted};
  margin-bottom: ${spacing.xs};
`

export const Endereco = styled.p`
  font-size: 14px;
  color: ${color.textLight};
`

export const Proprietario = styled.div`
  padding: ${spacing.lg};
  background: ${color.backgroundDark};
  min-width: 220px;
`

export const ProprietarioTitle = styled.h2`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.md};
  padding-bottom: ${spacing.sm};
  border-bottom: 1px solid ${color.border};
`

export const Nome = styled.p`
  font-size: 15px;
  font-weight: 500;
  color: ${color.text};
  margin-bottom: ${spacing.sm};
`

export const Telefone = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.sm};
  display: flex;
  align-items: center;
  gap: ${spacing.xs};
`

export const Email = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  word-break: break-all;
`

export const Icons = styled.div`
  display: flex;
  gap: ${spacing.sm};
  position: absolute;
  top: ${spacing.md};
  right: ${spacing.md};

  i {
    cursor: pointer;
    padding: ${spacing.sm};
    background: ${color.cardBg};
    color: ${color.textLight};
    transition: all 0.2s ease;

    &:hover {
      color: ${color.primary};
    }
  }
`

export const Sections = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: ${spacing.xxl} ${spacing.lg};
`

export const TituloSecao = styled.h1`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.secondary};
  margin-bottom: ${spacing.lg};
  display: flex;
  align-items: center;
  gap: ${spacing.sm};

  &:before {
    content: '';
    width: 3px;
    height: 24px;
    background: ${color.primary};
  }
`

export const Interesses = styled.div`
  background: ${color.cardBg};
  padding: ${spacing.xl};
  margin-bottom: ${spacing.xl};
  border: 1px solid ${color.border};
`

export const Permutas = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: ${spacing.xl};

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const PermutaSection = styled.div`
  background: ${color.cardBg};
  padding: ${spacing.xl};
  border: 1px solid ${color.border};
`

export const MatchCard = styled.div`
  padding: ${spacing.md};
  border: 1px solid ${color.border};
  margin-bottom: ${spacing.md};
  transition: all 0.2s ease;
  background: ${color.background};

  &:hover {
    border-color: ${color.success};
  }

  &:last-child {
    margin-bottom: 0;
  }
`

export const MatchCardTitle = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: ${color.text};
  margin-bottom: ${spacing.sm};
`

export const MatchCardDetail = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.xs};
`

export const MatchCardValue = styled.p`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.success};
  margin-top: ${spacing.sm};
`

export const MatchBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: 4px 10px;
  background: ${color.success};
  color: ${color.textInverse};
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: ${spacing.sm};
`

export const ActionButtons = styled.div`
  display: flex;
  gap: ${spacing.sm};
  margin-top: ${spacing.lg};
`

export const ActionButton = styled.button<{ $variant?: 'edit' | 'delete' }>`
  display: inline-flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.sm} ${spacing.lg};
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  
  ${({ $variant }) => $variant === 'delete' ? `
    background: ${color.danger};
    color: white;
    
    &:hover {
      opacity: 0.9;
    }
  ` : `
    background: ${color.primary};
    color: white;
    
    &:hover {
      background: ${color.primaryLight};
    }
  `}
`
