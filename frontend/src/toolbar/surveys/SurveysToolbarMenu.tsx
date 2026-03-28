import { useValues } from 'kea'

import { SurveyQuickCreate } from './QuickCreate/SurveyQuickCreate'
import { SurveyListView } from './SurveyListView'
import { SurveyLivePreview } from './SurveyLivePreview'
import { surveysToolbarLogic } from './surveysToolbarLogic'

export function SurveysToolbarMenu(): JSX.Element {
    const { isCreating } = useValues(surveysToolbarLogic)

    return (
        <>
            <SurveyLivePreview />
            {isCreating ? <SurveyQuickCreate /> : <SurveyListView />}
        </>
    )
}
