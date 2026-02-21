import { styled } from 'styled-components'

import { Link } from 'react-router-dom'

import { color } from '../../../styles'

export const LinkTo = styled(Link)`
  text-decoration: none;
  color: ${color.logoPrimary};
`
