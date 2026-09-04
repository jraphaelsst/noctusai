import { styled } from 'styled-components'
import { spacing, breakpoints, color } from '../../styles'

export const CardsContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${spacing.lg};
  margin-top: ${spacing.lg};

  @media (max-width: ${breakpoints.desktop}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
  }
`

export const PageHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${spacing.lg};
`

export const SearchBar = styled.div`
  display: flex;
  gap: ${spacing.md};
  margin-bottom: ${spacing.lg};
`

export const FilterContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.lg};
`

export const FilterTag = styled.button<{ active?: boolean }>`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${(props) => (props.active ? color.primary : color.border)};
  background: ${(props) => (props.active ? color.primary : 'transparent')};
  color: ${(props) => (props.active ? color.textInverse : color.text)};
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: ${color.primary};
  }
`

export const EmptyState = styled.div`
  text-align: center;
  padding: ${spacing.xxl};
  color: ${color.textLight};

  h3 {
    margin-bottom: ${spacing.md};
    color: ${color.text};
  }

  p {
    margin-bottom: ${spacing.lg};
  }
`
