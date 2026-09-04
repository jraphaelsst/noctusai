import { styled } from 'styled-components'
import { Link } from 'react-router-dom'
import { color, radius, spacing } from '../../styles'

export const LinkTo = styled(Link)`
  color: ${color.primary};
  font-size: 14px;
  font-weight: 500;
  margin-top: ${spacing.md};
  text-align: center;
  transition: all 0.2s ease;
  display: block;
  text-decoration: none;

  &:hover {
    color: ${color.primaryDark};
  }

  &:focus {
    outline: 2px solid ${color.primary};
    outline-offset: 2px;
    border-radius: ${radius.sm};
  }
`
