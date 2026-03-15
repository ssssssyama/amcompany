' =============================================================================
' TestEvidence VBA Lite — テストエビデンス自動化（簡易版）
' =============================================================================
' Excel VBA + Selenium Basic (Edge WebDriver) で動作するため、
' Python等の追加ソフトウェアインストールが不要。
'
' 【必要なもの】
' - Microsoft Edge（Windows標準搭載）
' - Selenium Basic（https://github.com/nicolestandifer3/SeleniumBasic-VBA からDL）
' - 本VBAコード（標準モジュールにインポート）
'
' 【対応操作】navigate / click / input / select / wait
' 【対応検証】screenshot / text / visible
' 【制限事項】DB検証・正規表現検証・複数シート一括実行は Pro版で対応
' =============================================================================

Option Explicit

' --- 定数 ---
Private Const COL_NO As String = "A"
Private Const COL_ITEM As String = "B"
Private Const COL_ACTION As String = "C"
Private Const COL_SELECTOR As String = "D"
Private Const COL_INPUT As String = "E"
Private Const COL_VERIFY_TYPE As String = "F"
Private Const COL_VERIFY_TARGET As String = "G"
Private Const COL_EXPECTED As String = "H"
Private Const COL_RESULT As String = "I"
Private Const COL_EVIDENCE As String = "J"
Private Const COL_NOTE As String = "K"

Private Const DATA_START_ROW As Long = 7
Private Const SCREENSHOT_WIDTH As Long = 400
Private Const SCREENSHOT_HEIGHT As Long = 250

' --- メインルーチン ---
Public Sub RunTestEvidence()
    ' Selenium Basic の参照設定が必要:
    ' VBEメニュー → ツール → 参照設定 → Selenium Type Library にチェック

    Dim driver As Object ' Selenium.WebDriver
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim row As Long
    Dim okCount As Long, ngCount As Long, skipCount As Long
    Dim screenshotDir As String
    Dim startTime As Date

    On Error GoTo ErrorHandler

    startTime = Now
    Set ws = ActiveSheet

    ' スクリーンショット保存先
    screenshotDir = ThisWorkbook.Path & "\screenshots"
    If Dir(screenshotDir, vbDirectory) = "" Then
        MkDir screenshotDir
    End If

    ' 最終行を取得
    lastRow = ws.Cells(ws.Rows.Count, COL_NO).End(xlUp).row
    If lastRow < DATA_START_ROW Then
        MsgBox "テストステップが見つかりません。" & vbCrLf & _
               DATA_START_ROW & "行目以降にデータを入力してください。", vbExclamation
        Exit Sub
    End If

    ' Edge WebDriver を起動
    Set driver = CreateObject("Selenium.EdgeDriver")
    driver.AddArgument "--start-maximized"
    driver.Start

    Application.StatusBar = "テストエビデンス実行中..."
    Application.ScreenUpdating = False

    okCount = 0
    ngCount = 0
    skipCount = 0

    ' 各ステップを実行
    For row = DATA_START_ROW To lastRow
        ' No.が空なら行をスキップ
        If IsEmpty(ws.Range(COL_NO & row).Value) Then GoTo NextRow

        Dim stepNo As String
        Dim action As String
        Dim selector As String
        Dim inputVal As String
        Dim verifyType As String
        Dim verifyTarget As String
        Dim expected As String

        stepNo = CStr(ws.Range(COL_NO & row).Value)
        action = LCase(Trim(CStr(ws.Range(COL_ACTION & row).Value & "")))
        selector = Trim(CStr(ws.Range(COL_SELECTOR & row).Value & ""))
        inputVal = Trim(CStr(ws.Range(COL_INPUT & row).Value & ""))
        verifyType = LCase(Trim(CStr(ws.Range(COL_VERIFY_TYPE & row).Value & "")))
        verifyTarget = Trim(CStr(ws.Range(COL_VERIFY_TARGET & row).Value & ""))
        expected = Trim(CStr(ws.Range(COL_EXPECTED & row).Value & ""))

        Application.StatusBar = "Step " & stepNo & " 実行中..."

        Dim passed As Variant  ' True/False/Null
        Dim message As String
        Dim screenshotPath As String
        passed = Null
        message = ""
        screenshotPath = ""

        ' --- ブラウザ操作 ---
        On Error Resume Next
        Err.Clear

        Select Case action
            Case "navigate"
                driver.Get inputVal
                WaitForPageLoad driver

            Case "click"
                driver.FindElementByCss(selector).Click
                WaitForPageLoad driver

            Case "input"
                driver.FindElementByCss(selector).Clear
                driver.FindElementByCss(selector).SendKeys inputVal

            Case "select"
                Dim selectEl As Object
                Set selectEl = driver.FindElementByCss(selector)
                selectEl.AsSelect.SelectByValue inputVal

            Case "wait"
                Dim waitMs As Long
                If inputVal <> "" Then waitMs = CLng(inputVal) Else waitMs = 1000
                Sleep waitMs

            Case ""
                ' 操作なし（検証のみ）

            Case Else
                message = "未対応の操作: " & action & " (Pro版で対応)"
        End Select

        If Err.Number <> 0 Then
            passed = False
            message = "操作エラー: " & Err.Description
            Err.Clear
        End If
        On Error GoTo ErrorHandler

        ' --- スクリーンショット ---
        If action <> "" Or verifyType = "screenshot" Then
            screenshotPath = screenshotDir & "\step_" & stepNo & ".png"
            On Error Resume Next
            driver.TakeScreenshot.SaveAs screenshotPath
            If Err.Number <> 0 Then
                screenshotPath = ""
                Err.Clear
            End If
            On Error GoTo ErrorHandler
        End If

        ' --- 検証 ---
        If Not (passed = False) Then  ' 操作エラー時は検証をスキップ
            On Error Resume Next
            Err.Clear

            Select Case verifyType
                Case "text"
                    Dim actualText As String
                    actualText = driver.FindElementByCss(verifyTarget).Text
                    If Err.Number <> 0 Then
                        passed = False
                        message = "要素が見つかりません: " & verifyTarget
                        Err.Clear
                    ElseIf actualText = expected Then
                        passed = True
                        message = "OK: '" & actualText & "'"
                    Else
                        passed = False
                        message = "NG: 期待値='" & expected & "', 実際='" & actualText & "'"
                    End If

                Case "visible"
                    Dim el As Object
                    Set el = driver.FindElementByCss(verifyTarget)
                    If Err.Number <> 0 Then
                        passed = False
                        message = "要素が見つかりません: " & verifyTarget
                        Err.Clear
                    ElseIf el.Displayed Then
                        passed = True
                        message = "OK: 要素は表示されています"
                    Else
                        passed = False
                        message = "NG: 要素が表示されていません"
                    End If

                Case "screenshot"
                    passed = True
                    message = "スクリーンショット取得"

                Case "db"
                    passed = Null
                    message = "DB検証はPro版で対応 (Docker版をご利用ください)"

                Case ""
                    If IsNull(passed) Then
                        passed = True
                        message = "操作完了"
                    End If

                Case Else
                    passed = Null
                    message = "未対応の検証: " & verifyType & " (Pro版で対応)"
            End Select

            On Error GoTo ErrorHandler
        End If

        ' --- 結果書き込み ---
        WriteResult ws, row, passed, message, screenshotPath

        If IsNull(passed) Then
            skipCount = skipCount + 1
        ElseIf passed = True Then
            okCount = okCount + 1
        Else
            ngCount = ngCount + 1
        End If

NextRow:
    Next row

    ' ブラウザを閉じる
    driver.Quit
    Set driver = Nothing

    Application.ScreenUpdating = True
    Application.StatusBar = False

    ' 結果サマリー
    Dim total As Long
    total = okCount + ngCount + skipCount
    MsgBox "テスト完了!" & vbCrLf & vbCrLf & _
           "OK: " & okCount & " / " & total & vbCrLf & _
           "NG: " & ngCount & " / " & total & vbCrLf & _
           "SKIP: " & skipCount & " / " & total & vbCrLf & vbCrLf & _
           "実行時間: " & Format(Now - startTime, "hh:nn:ss"), _
           IIf(ngCount > 0, vbExclamation, vbInformation), _
           "TestEvidence Lite"
    Exit Sub

ErrorHandler:
    Application.ScreenUpdating = True
    Application.StatusBar = False
    If Not driver Is Nothing Then
        On Error Resume Next
        driver.Quit
        Set driver = Nothing
    End If
    MsgBox "エラーが発生しました:" & vbCrLf & _
           "エラー番号: " & Err.Number & vbCrLf & _
           "内容: " & Err.Description, vbCritical, "TestEvidence Lite"
End Sub


' --- 結果をセルに書き込み ---
Private Sub WriteResult(ws As Worksheet, row As Long, passed As Variant, _
                        message As String, screenshotPath As String)
    Dim resultCell As Range
    Set resultCell = ws.Range(COL_RESULT & row)

    If IsNull(passed) Then
        resultCell.Value = "SKIP"
        resultCell.Interior.Color = RGB(255, 235, 156)  ' 黄色
        resultCell.Font.Color = RGB(156, 101, 0)
        resultCell.Font.Bold = True
    ElseIf passed = True Then
        resultCell.Value = "OK"
        resultCell.Interior.Color = RGB(198, 239, 206)  ' 緑
        resultCell.Font.Color = RGB(0, 97, 0)
        resultCell.Font.Bold = True
    Else
        resultCell.Value = "NG"
        resultCell.Interior.Color = RGB(255, 199, 206)  ' 赤
        resultCell.Font.Color = RGB(156, 0, 6)
        resultCell.Font.Bold = True
    End If

    ' メッセージを備考欄に書き込み
    If message <> "" Then
        Dim noteCell As Range
        Set noteCell = ws.Range(COL_NOTE & row)
        Dim existing As String
        existing = CStr(noteCell.Value & "")
        If existing <> "" Then
            noteCell.Value = existing & vbLf & message
        Else
            noteCell.Value = message
        End If
    End If

    ' スクリーンショットをエビデンス列に貼付
    If screenshotPath <> "" And Dir(screenshotPath) <> "" Then
        Dim pic As Shape
        Dim evidenceCell As Range
        Set evidenceCell = ws.Range(COL_EVIDENCE & row)

        Set pic = ws.Shapes.AddPicture( _
            Filename:=screenshotPath, _
            LinkToFile:=msoFalse, _
            SaveWithDocument:=msoTrue, _
            Left:=evidenceCell.Left + 2, _
            Top:=evidenceCell.Top + 2, _
            Width:=SCREENSHOT_WIDTH, _
            Height:=SCREENSHOT_HEIGHT)

        ' 行の高さをスクリーンショットに合わせる
        ws.Rows(row).RowHeight = SCREENSHOT_HEIGHT + 10
    End If
End Sub


' --- ページロード完了を待つ ---
Private Sub WaitForPageLoad(driver As Object)
    Dim timeout As Long
    timeout = 10000  ' 10秒
    Dim startTime As Long
    startTime = GetTickCount()

    Do While GetTickCount() - startTime < timeout
        On Error Resume Next
        Dim readyState As String
        readyState = driver.ExecuteScript("return document.readyState")
        If Err.Number = 0 And readyState = "complete" Then
            On Error GoTo 0
            Exit Sub
        End If
        Err.Clear
        On Error GoTo 0
        Sleep 100
    Loop
End Sub


' --- Win32 API ---
#If VBA7 Then
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
    Private Declare PtrSafe Function GetTickCount Lib "kernel32" () As Long
#Else
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
    Private Declare Function GetTickCount Lib "kernel32" () As Long
#End If
