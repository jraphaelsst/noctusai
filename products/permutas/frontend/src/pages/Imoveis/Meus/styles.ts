import { styled } from 'styled-components'
import { Link } from 'react-router-dom'
import { color, radius, spacing } from '../../../styles'

export const LinkTo = styled(Link)`
  text-decoration: none;
  color: inherit;
  display: block;

  &:hover {
    text-decoration: none;
  }
`

export const PageActions = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${spacing.lg};
`

export const SearchInput = styled.input`
  padding: 10px 16px;
  border-radius: ${radius.md};
  border: 1px solid ${color.border};
  background: ${color.background};
  width: 300px;
  font-size: 14px;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`
