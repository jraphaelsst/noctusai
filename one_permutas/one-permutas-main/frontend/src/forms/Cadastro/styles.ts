import { styled } from 'styled-components'
import { Link } from 'react-router-dom'

export const LinkTo = styled(Link)`
  opacity: 0.7;
  color: #eee;
  margin-top: 24px;
  font-size: 14px;
  transition: all 0.3s ease;

  &:hover {
    transform: scale(0.95);
  }

  &:focus {
    transform: scale(1.02);
    outline: none;
    border: 1px solid #ddd;
    padding: 4px;
  }
`
