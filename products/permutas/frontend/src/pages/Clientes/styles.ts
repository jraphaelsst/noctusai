import { styled } from 'styled-components'
import { color, spacing, breakpoints } from '../../styles'

export const Container = styled.div`
  padding: ${spacing.lg};
`

export const ClientesGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${spacing.lg};

  @media (max-width: ${breakpoints.desktop}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const SearchContainer = styled.div`
  display: flex;
  gap: ${spacing.md};
  margin-bottom: ${spacing.lg};
`

export const SearchInput = styled.input`
  flex: 1;
  max-width: 400px;
  padding: 12px 16px;
  border: 1px solid ${color.border};
  background: ${color.cardBg};
  font-size: 14px;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`
